#!/bin/bash
# MLX gate with four MLX servers (8605-8608) round-robin; the MLX server answers one request at a time.
exec >> /root/v50p/mlx_gate.log 2>&1
while pgrep -f "^python3 equiv_mlx.py" >/dev/null; do sleep 20; done
echo "=== rito MLX com 4 servidores inicio $(date -u +%T)"
cd /root/v50p
export URL=http://127.0.0.1:8605,http://127.0.0.1:8606,http://127.0.0.1:8607,http://127.0.0.1:8608 PAR=8 SKIP_READ_ONCE=1 OUT=/root/v50p/release_r4_mlx
mkdir -p $OUT
python3 release_eval.py && python3 release_eval_extra_rtx.py && OUT=/root/v50p/release_r4_mlx READOUT=r4_readout python3 guard_big_served_rtx.py
python3 quant_gate.py release_r4 release_r4_mlx --no-read-once > quant_gate_mlx.json; tail -25 quant_gate_mlx.json
echo MLX_GATE_DONE $(date -u +%T)
python3 /root/backup_hf.py mlx-gate
