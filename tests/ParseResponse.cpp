#include <fstream>
#include <iostream>
#include <iterator>
#include <string>

#include "http/HttpParser.h"

int main(int argc, char** argv) {
  if (argc != 3) return 2;
  std::ifstream input(argv[1], std::ios::binary);
  if (!input) return 2;
  std::string wire{std::istreambuf_iterator<char>(input),
                   std::istreambuf_iterator<char>()};
  gateway::http::HttpParser parser(gateway::http::MessageKind::kResponse);
  auto result = parser.parseBytes(wire);
  if (result.status == gateway::http::ParseStatus::kNeedMore)
    result = parser.finishInput();
  const bool complete = result.status == gateway::http::ParseStatus::kComplete;
  std::cout << "complete=" << complete << " body=" << parser.message().body
            << " error=" << result.errorCode << '\n';
  return complete == (std::string(argv[2]) == "complete") ? 0 : 1;
}
