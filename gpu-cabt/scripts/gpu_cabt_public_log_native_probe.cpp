#include <iostream>
#include "All.h"
#include "ApiJson.h"

int main() {
    InitializeAll();
    int count = 0;
    if (!(std::cin >> count)) return 2;
    for (int i = 0; i < count; ++i) {
        int actor = 0, type = 0, param_count = 0;
        if (!(std::cin >> actor >> type >> param_count)) return 3;
        Log log((LogType)type);
        for (int p = 0; p < 7; ++p) {
            int value = 0;
            if (!(std::cin >> value)) return 4;
            if (p < param_count) log.add(value);
        }
        JsonBuilder json;
        LogJson(json, log, actor, false);
        std::cout.write(reinterpret_cast<const char*>(json.buf.data()), (std::streamsize)json.buf.size());
        std::cout << '\n';
    }
    return 0;
}
