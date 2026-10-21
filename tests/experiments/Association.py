"""Post-drain connection-instance audit; never compares clocks across processes."""
from collections import defaultdict


def associate(rows, records, *, cell_id, host_pid, target_port, client_address='127.0.0.1', target_address='127.0.0.1'):
    if not cell_id or not isinstance(host_pid,int) or host_pid<=0:
        raise RuntimeError('association lifecycle scope missing')
    if client_address!='127.0.0.1' or target_address!='127.0.0.1' or not isinstance(target_port,int) or not 0<target_port<65536:
        raise RuntimeError('association requires one IPv4 loopback target')
    clients=defaultdict(list);hosts=defaultdict(list);excluded={};ids=set();sessions=set()
    def interval(row,start,end):
        a,b=row.get(start),row.get(end)
        if not isinstance(a,int) or not isinstance(b,int) or a<=0 or b<a:
            raise RuntimeError('association missing or invalid interval')
        return a,b
    def port(row):
        value=row.get('client_port')
        if not isinstance(value,int) or not 0<value<65536:raise RuntimeError('association source port missing')
        return value
    for row in rows:
        identifier=row.get('id')
        if not isinstance(identifier,str) or not identifier.startswith(cell_id+'-') or identifier in ids:
            raise RuntimeError('association duplicate or foreign attempt')
        ids.add(identifier)
        if row.get('outcome') in ('not_sent','not_started'):
            if row.get('connect') or row.get('client_port') or row.get('send'):raise RuntimeError('unissued attempt has connection')
            excluded[identifier]=row['outcome'];continue
        if not row.get('connect'):
            if row.get('client_port') or row.get('send') or row.get('outcome') not in ('transport_failure','interrupted','client_deadline'):
                raise RuntimeError('unproven connection identity')
            excluded[identifier]='not_established';continue
        if row.get('target_port')!=target_port:raise RuntimeError('association foreign target')
        interval(row,'connect','closed');clients[port(row)].append(row)
    for record in records:
        identifier=record.get('id')
        if not isinstance(identifier,int) or identifier in sessions:raise RuntimeError('association duplicate host session')
        sessions.add(identifier);interval(record,'accepted','finished');hosts[port(record)].append(record)
    if clients.keys()!=hosts.keys():raise RuntimeError('association unmatched host or client')
    mapping={};consumed=set()
    def ordered(group,start,end):
        result=sorted(group,key=lambda row:row[start])
        for previous,current in zip(result,result[1:]):
            if previous[start]==current[start] or previous[end]>current[start]:
                raise RuntimeError('association equal ordering or overlapping connections')
        return result
    for source_port,group in clients.items():
        left=ordered(group,'connect','closed');right=ordered(hosts[source_port],'accepted','finished')
        if len(left)!=len(right):raise RuntimeError('association connection count mismatch')
        for row,record in zip(left,right):
            if record['id'] in consumed:raise RuntimeError('association repeated host consumption')
            consumed.add(record['id']);mapping[row['id']]=record
    if consumed!=sessions or len(mapping)+len(excluded)!=len(rows):raise RuntimeError('association incomplete consumption')
    return mapping,excluded
