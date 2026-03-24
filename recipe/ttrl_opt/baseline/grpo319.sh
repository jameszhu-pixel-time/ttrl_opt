#!/bin/bash
#export VLLM_ATTENTION_BACKEND=XFORMERS
unset VLLM_ATTENTION_BACKEND
export VLLM_USE_V1=1

# ------------------------------------------------------------

DATE=$(date +%m%d)
TIME_TAG=$(date +%H%M%S)

TASK="test-OR"
BACKBONE="Qwen3-4B-ins"
ADVANTAGE="grpo"

K=16
MAX_PROMPT_LENGTH=2048
MAX_RESPONSE_LENGTH=$((1024 * $K))
if [ "$K" -gt 8 ]; then
  N=4
else
  N=16
fi

EPISODE=2
DATA_TRAIN_BATCH_SIZE=32
N_VOTES_PER_PROMPT=32
## 64 生成
N_SAMPLES_PER_PROMPT=16
# 32 用于投票
MINI_BATCH_SIZE=32
MICRO_BATCH_SIZE=1

Traindata="/DATA/disk2/zhurui/TTRL/verl/data/SIRL-train/train.parquet"
Testdata="/DATA/disk2/zhurui/TTRL/verl/data/SIRL-train/test.parquet"
BACKBONE_PATH="/DATA/disk1/chenyitian/checkpoints/Qwen3-4B-Instruct-2507"

MODEL="${TASK}-${BACKBONE}"
EXPERIMENT="TTRL-Len@${K}k"

WANDB_PROJECT="TTRL-verl"
LOG_NAME="${DATE}-${EXPERIMENT}-${MODEL}-${ADVANTAGE}"
OUTPUT_DIR="checkpoints/${WANDB_PROJECT}/${MODEL}/${DATE}/${EXPERIMENT}-${ADVANTAGE}-${TIME_TAG}"
LOG_FILE="log/run_$(date +%Y%m%d_%H%M%S).log"
# ------------------------------------------------------------
python -m verl.trainer.main_exp_ppo \
--config-name='ppo_trainer_ttrl.yaml'\
  data.train_files=["$Traindata"] \
  data.val_files=["$Testdata"] \
  data.max_prompt_length=$MAX_PROMPT_LENGTH \
  data.max_response_length=$MAX_RESPONSE_LENGTH \
  data.train_batch_size=$DATA_TRAIN_BATCH_SIZE \
  data.filter_overlong_prompts=True \
  data.truncation='error' \
  actor_rollout_ref.model.path=$BACKBONE_PATH \
  actor_rollout_ref.model.enable_gradient_checkpointing=True \
  actor_rollout_ref.model.use_remove_padding=True \
  actor_rollout_ref.actor.ppo_mini_batch_size=$MINI_BATCH_SIZE \
  actor_rollout_ref.actor.ppo_micro_batch_size_per_gpu=$MICRO_BATCH_SIZE \
  actor_rollout_ref.actor.use_kl_loss=False \
  algorithm.use_kl_in_reward=True \
  algorithm.kl_ctrl.kl_coef=0.0005 \
  actor_rollout_ref.actor.optim.lr=5e-7 \
  actor_rollout_ref.actor.optim.lr_warmup_steps_ratio=0.03 \
  actor_rollout_ref.actor.optim.warmup_style='cosine' \
  actor_rollout_ref.actor.fsdp_config.param_offload=True \
  actor_rollout_ref.actor.fsdp_config.optimizer_offload=True \
  actor_rollout_ref.actor.ppo_max_token_len_per_gpu=$((MAX_PROMPT_LENGTH + MAX_RESPONSE_LENGTH)) \
  actor_rollout_ref.ref.log_prob_micro_batch_size_per_gpu=$MICRO_BATCH_SIZE \
  actor_rollout_ref.ref.fsdp_config.param_offload=True \
  actor_rollout_ref.rollout.name=vllm \
  actor_rollout_ref.rollout.temperature=1.0 \
  actor_rollout_ref.rollout.enforce_eager=False \
  actor_rollout_ref.rollout.free_cache_engine=False \
  actor_rollout_ref.rollout.log_prob_micro_batch_size_per_gpu=$MICRO_BATCH_SIZE \
  actor_rollout_ref.rollout.tensor_model_parallel_size=4 \
  actor_rollout_ref.rollout.gpu_memory_utilization=0.5 \
  actor_rollout_ref.rollout.n=$N_SAMPLES_PER_PROMPT \
  actor_rollout_ref.rollout.val_kwargs.do_sample=True \
  actor_rollout_ref.rollout.val_kwargs.n=$N \
  actor_rollout_ref.rollout.val_kwargs.top_p=0.95 \
  actor_rollout_ref.rollout.val_kwargs.temperature=0.6 \
  actor_rollout_ref.rollout.max_model_len=$((MAX_PROMPT_LENGTH + MAX_RESPONSE_LENGTH)) \
  actor_rollout_ref.rollout.max_num_batched_tokens=$((MAX_PROMPT_LENGTH + MAX_RESPONSE_LENGTH)) \
  algorithm.adv_estimator=$ADVANTAGE \
  reward_model.reward_manager=batch \
  custom_reward_function.path="recipe/ttrl_opt/group_score_gurobi.py" \
  custom_reward_function.name=compute_score_simplified \
  ttrl.enable=False \
  trainer.logger=['console','wandb'] \
  trainer.project_name=$WANDB_PROJECT \
  trainer.experiment_name=$LOG_NAME \
  trainer.val_before_train=False \
  trainer.n_gpus_per_node=8 \
  trainer.nnodes=1 \
  trainer.save_freq=50 \
  trainer.test_freq=2 \
  trainer.max_actor_ckpt_to_keep=0 \
  trainer.max_critic_ckpt_to_keep=0 \
  trainer.default_local_dir=$OUTPUT_DIR \
  trainer.total_epochs=$EPISODE "$@" \
  > "$LOG_FILE"  2>&1 
#+data.suffix_prompt='"\nPlease reason step by step, and put your final answer within \boxed{}."' \
echo "Output directory: $OUTPUT_DIR"

# critic.optim.lr=9e-6 \
#   critic.model.use_remove_padding=True \
#   critic.model.path=$BACKBONE_PATH \
#   critic.model.enable_gradient_checkpointing=True \
#   critic.ppo_micro_batch_size_per_gpu=$MICRO_BATCH_SIZE \
#   critic.model.fsdp_config.param_offload=False \
#   critic.model.fsdp_config.optimizer_offload=False \
# ttrl.n_votes_per_prompt=$N_VOTES_PER_PROMPT \
#   ttrl.n_samples_per_prompt=$N_SAMPLES_PER_PROMPT \