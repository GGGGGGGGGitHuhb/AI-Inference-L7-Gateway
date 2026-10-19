#include <iostream>
#include <stdexcept>
#include <string_view>

#include "app/GatewayConfig.h"
#include "gateway/GatewayRuntime.h"

int main(int argc, char** argv) {
  if (argc == 2 && std::string_view(argv[1]) == "--help") {
    std::cout << "Usage: ai-inference-gateway --config <path>\n";
    return 0;
  }

  if (argc != 3 || std::string_view(argv[1]) != "--config" ||
      std::string_view(argv[2]).starts_with("--")) {
    std::cerr << "Invalid arguments; use --help\n";
    return 2;
  }
  gateway::app::GatewayConfig config;
  try {
    config = gateway::app::readConfig(argv[2]);
  } catch (const std::invalid_argument&) {
    std::cerr << "Invalid configuration\n";
    return 2;
  } catch (...) {
    std::cerr << "Configuration resource failure\n";
    return 1;
  }
  try {
    gateway::gateway_api::GatewayRuntime runtime(config);
    const auto port = runtime.startListener();
    std::cout << "READY " << config.listenAddress << ":" << port << std::endl;
    runtime.runGateway();
    return 0;
  } catch (...) {
    std::cerr << "Gateway runtime failure\n";
    return 1;
  }
}
