#!/bin/bash
exec >> /root/v50p/mlx_gate.log 2>&1
echo "=== retomada com 2 servidores (cache 2 GB) $(date -u +%T)"
cd /root/v50p
export URL=http://127.0.0.1:8605,http://127.0.0.1:8606 PAR=4 SKIP_READ_ONCE=1 OUT=/root/v50p/release_r4_mlx
python3 release_eval_multi_only.py && python3 release_eval_extra_rtx.py && OUT=/root/v50p/release_r4_mlx READOUT=r4_readout python3 guard_big_served_rtx.py
python3 quant_gate.py release_r4 release_r4_mlx --no-read-once > quant_gate_mlx.json; tail -25 quant_gate_mlx.json
echo MLX_GATE3_DONE $(date -u +%T)
python3 /root/backup_hf.py mlx-gate
