#!/bin/bash
# MLX build gate (PREREG_quantized.md), with MLX on the Linux GPU (CUDA backend), as for Ekbasis-27B-MLX-4bit.
exec >> /root/v50p/mlx_gate.log 2>&1
cd /root/Skopos-R4-27B-MLX-4bit
setsid /root/mlx_venv/bin/python mlx_serve.py /root/Skopos-R4-27B-MLX-4bit --port 8605 > /root/v50p/mlx_serve.log 2>&1 < /dev/null &
for i in $(seq 1 120); do grep -qi "ready\|listening\|serving" /root/v50p/mlx_serve.log && break; sleep 5; done
sleep 5; tail -3 /root/v50p/mlx_serve.log
cd /root/v50p
sed -e "s|http://127.0.0.1:8603/v1/evaluate|http://127.0.0.1:8605/v1/systemone|" -e "s|cf.ThreadPoolExecutor(8)|cf.ThreadPoolExecutor(2)|" equiv_r4.py > equiv_mlx.py
echo "equivalencia MLX x trainer bf16 $(date -u +%T)"; python3 equiv_mlx.py
export URL=http://127.0.0.1:8605 PAR=2 SKIP_READ_ONCE=1 OUT=/root/v50p/release_r4_mlx
mkdir -p $OUT
echo "rito MLX inicio $(date -u +%T)"
python3 release_eval.py && python3 release_eval_extra_rtx.py && OUT=/root/v50p/release_r4_mlx READOUT=r4_readout python3 guard_big_served_rtx.py
python3 quant_gate.py release_r4 release_r4_mlx --no-read-once > quant_gate_mlx.json; tail -25 quant_gate_mlx.json
echo MLX_GATE_DONE $(date -u +%T)
python3 /root/backup_hf.py mlx-gate
