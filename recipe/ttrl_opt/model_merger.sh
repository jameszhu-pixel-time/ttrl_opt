step=150
python -m verl.model_merger merge \
    --backend fsdp \
    --local_dir /DATA/disk2/zhurui/TTRL/verl/checkpoints/TTRL-verl/test-OR-Qwen3-4B-ins/0320/TTRL-Len@16k-grpo-140344/global_step_150 \
    --target_dir /DATA/disk2/zhurui/TTRL/verl/merged_model/qwen3_4b_ins_step$step

/DATA/disk2/zhurui/TTRL/verl/checkpoints/TTRL-verl/test-OR-Qwen3-4B-ins/0320/TTRL-Len@16k-grpo-140344/global_step_150
step=150
python -m verl.model_merger merge \
    --backend fsdp \
    --local_dir /DATA/disk2/zhurui/TTRL/verl/checkpoints/TTRL-verl/test-OR-Qwen3-4B-ins/0320/TTRL-Len@16k-reinforce_plus_plus-131126/global_step_150/actor \
    --target_dir /DATA/disk2/zhurui/TTRL/verl/merged_model/qwen3_4b_ins_step$step