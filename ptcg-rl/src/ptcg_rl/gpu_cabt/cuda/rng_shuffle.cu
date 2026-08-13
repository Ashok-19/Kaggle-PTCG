// Generic GPU-training RNG primitives. No official CABT source is embedded here.
// Keep this translation unit NVRTC-freestanding: the local qualification path
// intentionally does not require a host CUDA toolkit or libc headers.
using uint32_t = unsigned int;
using uint64_t = unsigned long long;
using int32_t = int;
static_assert(sizeof(uint32_t) == 4, "uint32_t must be 32-bit");
static_assert(sizeof(uint64_t) == 8, "uint64_t must be 64-bit");
static_assert(sizeof(int32_t) == 4, "int32_t must be 32-bit");

namespace gpu_cabt {

static constexpr uint32_t M0 = 0xD2511F53u;
static constexpr uint32_t M1 = 0xCD9E8D57u;
static constexpr uint32_t W0 = 0x9E3779B9u;
static constexpr uint32_t W1 = 0xBB67AE85u;

__device__ __forceinline__ void mulhilo32(uint32_t a, uint32_t b, uint32_t* hi, uint32_t* lo) {
    const uint64_t product = static_cast<uint64_t>(a) * static_cast<uint64_t>(b);
    *hi = static_cast<uint32_t>(product >> 32);
    *lo = static_cast<uint32_t>(product);
}

__device__ __forceinline__ void philox4x32_10(
    uint32_t& c0,
    uint32_t& c1,
    uint32_t& c2,
    uint32_t& c3,
    uint32_t k0,
    uint32_t k1
) {
    #pragma unroll
    for (int round_index = 0; round_index < 10; ++round_index) {
        uint32_t hi0, lo0, hi1, lo1;
        mulhilo32(M0, c0, &hi0, &lo0);
        mulhilo32(M1, c2, &hi1, &lo1);
        const uint32_t n0 = hi1 ^ c1 ^ k0;
        const uint32_t n1 = lo1;
        const uint32_t n2 = hi0 ^ c3 ^ k1;
        const uint32_t n3 = lo0;
        c0 = n0;
        c1 = n1;
        c2 = n2;
        c3 = n3;
        if (round_index != 9) {
            k0 += W0;
            k1 += W1;
        }
    }
}

__device__ __forceinline__ uint32_t philox_u32(
    uint64_t seed,
    uint64_t stream,
    uint64_t draw_index
) {
    const uint64_t block = draw_index >> 2;
    const uint32_t lane = static_cast<uint32_t>(draw_index & 3ull);
    uint32_t c0 = static_cast<uint32_t>(block);
    uint32_t c1 = static_cast<uint32_t>(block >> 32);
    uint32_t c2 = static_cast<uint32_t>(stream);
    uint32_t c3 = static_cast<uint32_t>(stream >> 32);
    philox4x32_10(
        c0,
        c1,
        c2,
        c3,
        static_cast<uint32_t>(seed),
        static_cast<uint32_t>(seed >> 32)
    );
    if (lane == 0u) return c0;
    if (lane == 1u) return c1;
    if (lane == 2u) return c2;
    return c3;
}

__device__ __forceinline__ uint32_t bounded_u32(
    uint64_t seed,
    uint64_t stream,
    uint64_t* draw_index,
    uint32_t bound
) {
    const uint32_t threshold = static_cast<uint32_t>(-bound) % bound;
    while (true) {
        const uint32_t value = philox_u32(seed, stream, (*draw_index)++);
        const uint64_t product = static_cast<uint64_t>(value) * static_cast<uint64_t>(bound);
        const uint32_t low = static_cast<uint32_t>(product);
        if (low >= threshold) {
            return static_cast<uint32_t>(product >> 32);
        }
    }
}

}  // namespace gpu_cabt

extern "C" __global__ void shuffle_decks(
    const int32_t* input_deck,
    int32_t* output_decks,
    uint64_t seed,
    uint64_t stream_base,
    int env_count,
    int deck_size
) {
    const int env_index = blockDim.x * blockIdx.x + threadIdx.x;
    if (env_index >= env_count) return;
    if (deck_size <= 0 || deck_size > 64) return;

    int32_t* row = output_decks + static_cast<long long>(env_index) * deck_size;
    for (int index = 0; index < deck_size; ++index) {
        row[index] = input_deck[index];
    }

    const uint64_t stream = stream_base + static_cast<uint64_t>(env_index);
    uint64_t draw_index = 0;
    for (int index = deck_size - 1; index > 0; --index) {
        const uint32_t swap_index = gpu_cabt::bounded_u32(
            seed, stream, &draw_index, static_cast<uint32_t>(index + 1)
        );
        const int32_t tmp = row[index];
        row[index] = row[swap_index];
        row[swap_index] = tmp;
    }
}
