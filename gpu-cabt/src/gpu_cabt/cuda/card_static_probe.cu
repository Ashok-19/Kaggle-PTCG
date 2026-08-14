extern "C" __global__ void gpu_cabt_card_static_probe(
    const gpu_cabt::SetupCardStatic* table,
    gc_i32 table_size,
    const gc_i32* card_ids,
    gc_u8* output,
    gc_i32 count
) {
    const gc_i32 index = (gc_i32)(blockDim.x * blockIdx.x + threadIdx.x);
    if (index >= count) return;
    const gc_i32 card_id = card_ids[index];
    gc_u8* row = output + (gc_i64)index * 4;
    if (card_id < 0 || card_id >= table_size) {
        row[0] = row[1] = row[2] = row[3] = 255;
        return;
    }
    const auto& entry = table[card_id];
    row[0] = entry.is_basic_pokemon;
    row[1] = entry.is_setup_doll;
    row[2] = entry.can_setup;
    row[3] = entry.can_setup_active;
}
