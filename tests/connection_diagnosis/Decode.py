"""Fixed native little-endian schema; exact tuple plus overlapping lifecycle only."""
from collections import defaultdict, Counter
import ipaddress
from pathlib import Path
import struct
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'capacity'))
from Common import rows, COLUMNS

HEADER = struct.Struct('<32Q')
RECORD = struct.Struct('<14Q' + 'IHH'*4 + '3Q9I32s20x')
assert RECORD.size == 256
MAGIC = 0x314543415254374C


def read_trace(folder):
    folder = Path(folder)
    header = HEADER.unpack((folder/'header.bin').read_bytes())
    if header[:3] != (MAGIC, 1, 256) or not 0 < header[3] <= 131071 or header[4] > header[3]:
        raise ValueError('trace schema/capacity')
    if header[5] or header[7] or header[4] != header[6]:
        raise ValueError('trace drop/duplicate/accept conservation')
    if any(header[i] for i in (10,11,12)):
        raise ValueError('trace live lifecycle at export')
    if not header[14] < header[15] <= header[16] <= header[15]+10_000_000_000:
        raise ValueError('trace export timing')
    result=[]
    paths=sorted(folder.glob('trace-*.bin'),key=lambda p:int(p.stem.split('-')[-1]))
    if [p.name for p in paths] != [f'trace-{i}.bin' for i in range(len(paths))]:
        raise ValueError('trace missing segment')
    for path in paths:
        data=path.read_bytes()
        if len(data)>1048576 or len(data)%256:
            raise ValueError('trace segment size')
        for v in RECORD.iter_unpack(data):
            times=list(v[2:14]);endpoints=[]
            for i in range(4):
                addr,port,reserved=v[14+3*i:17+3*i]
                endpoints.append([str(ipaddress.IPv4Address(addr)),port])
            sent=list(v[26:28]);reserved=v[28];active,closing,finished,kind,outcome,reason,side,error,flags=v[29:38]
            if v[0] != len(result)+1 or outcome not in range(1,6) or kind not in (1,2,3):
                raise ValueError('trace generation/classification')
            if not times[0] or not times[7] or times[7] < times[0] or (outcome==1 and (not times[8] or times[8]<times[7])):
                raise ValueError('trace lifetime missing/nonmonotonic')
            if any(t and not times[0] <= t <= times[7] for t in times[1:8]+[times[9]]):
                raise ValueError('trace stage outside lifecycle')
            stages=[t for t in times[:9] if t]
            if stages != sorted(stages):raise ValueError('trace stages out of order')
            if times[0] < header[14] or max(times) > header[15]:
                raise ValueError('trace clock outside process/export lifetime')
            if closing+finished>active and kind==1:raise ValueError('Gateway phase snapshot conservation')
            if flags & (1<<10):
                raise ValueError('trace reason truncated')
            result.append(dict(generation=v[0],session=v[1],times=times,endpoints=endpoints,sent=sent,
                               reserved=reserved,active=active,closing=closing,finished=finished,kind=kind,
                               outcome=outcome,reason=reason,first_side=side,error=error,flags=flags,
                               reason_text=v[38].split(b'\0')[0].decode('ascii'),process=[header[13],header[14]]))
    if len(result)!=header[4]:
        raise ValueError('trace count differs')
    return header,result


def tuple_key(local, peer):
    if not local or not peer or not local[1] or not peer[1]: return None
    return tuple(local[:2])+tuple(peer[:2])


class LifecycleIndex:
    def __init__(self, records, pair=0, reverse=False, kind=None):
        self.index=defaultdict(list)
        for record in records:
            if kind is not None and record['kind']!=kind:continue
            if record['flags'] & (3<<(pair*2)) != 3<<(pair*2):continue
            a,b=record['endpoints'][2*pair:2*pair+2]
            key=tuple_key(b,a) if reverse else tuple_key(a,b)
            if key is None:continue
            start=record['times'][2] if pair else record['times'][0]
            if not start:continue
            self.index[key].append((start,record['times'][7],record))
        for values in self.index.values(): values.sort(key=lambda v:v[0])

    def match(self, local,peer,start,end):
        key=tuple_key(local,peer)
        if key is None or start is None or end is None:return None,'missing-endpoint/lifetime'
        values=self.index.get(key,[])
        candidates=[v[2] for v in values if v[0] <= end and start <= v[1]]
        if len(candidates)!=1:return None, 'missing' if not candidates else 'ambiguous'
        return candidates[0], 'unique'


def correlate(root):
    root=Path(root)
    gw=[]
    for name in ('gateway-0','gateway-1'):
        _,records=read_trace(root/name);gw.extend(records)
    _,lb=read_trace(root/'l4lb')
    inbound=LifecycleIndex(lb,reverse=True,kind=2)
    gateway=LifecycleIndex(gw,reverse=True,kind=1)
    health=LifecycleIndex(lb,kind=3)
    endpoints={}
    for row in rows(root,'endpoints'):
        if row[0] in endpoints:raise ValueError('duplicate client endpoint identity')
        endpoints[row[0]]=row
    processes={r['name']:r['pid'] for r in __import__('json').loads((root/'processes.json').read_text())}
    for name in ('gateway-0','gateway-1','l4lb'):
        header=HEADER.unpack((root/name/'header.bin').read_bytes())
        if processes.get(name)!=header[13]:raise ValueError('trace process identity mismatch')
    outcomes=Counter();failures=[];matched_gateways=set();health_matches=set()
    for row in rows(root,'client'):
        v=dict(zip(COLUMNS,row))
        metadata=endpoints.pop(v['id'],None)
        if metadata is None or metadata[1:5] != [v['scheduled'],v['dispatch'],v['connect'],v['closed']]:
            raise ValueError('client endpoint identity/clock conservation')
        if v['phase']!='f' or v['outcome']!='transport_failure':continue
        meta=metadata
        explanation={'id':v['id'],'branch':'unknown'}
        if meta:
            session,status=inbound.match(meta[5],meta[6],meta[2],meta[4])
            explanation['l4_match']=status
            if session:
                explanation['l4']={k:session[k] for k in ('process','generation','first_side','error','reason_text','sent')}
                accepted,status=gateway.match(*session['endpoints'][2:4],session['times'][2],session['times'][7])
                explanation['gateway_match']=status
                if accepted:
                    explanation['gateway']={k:accepted[k] for k in ('process','generation','outcome','reason','reason_text','active','closing','finished','reserved','times')}
                    matched_gateways.add((tuple(accepted['process']),accepted['generation']))
                    explanation['branch']={2:'gateway_connection_limit',3:'gateway_reservation',4:'gateway_construction',5:'gateway_other'}.get(accepted['outcome'],'gateway_published')
        outcomes[explanation['branch']]+=1;failures.append(explanation)
    if endpoints:raise ValueError('foreign endpoint identities')
    for record in gw:
        probe,status=health.match(*record['endpoints'][:2][::-1],record['times'][0],record['times'][7])
        if probe:health_matches.add((tuple(record['process']),record['generation']))
    return {'formal_transport_failures':len(failures),'branches':dict(outcomes),'failures':failures,
            'gateway_records':len(gw),'explicit_health_gateway_matches':len(health_matches),
            'note':'Unmatched accepted connections remain unknown; no HTTP ID inferred from session number or proximity.'}
