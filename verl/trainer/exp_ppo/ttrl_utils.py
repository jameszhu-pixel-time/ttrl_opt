# Copyright 2025 TTRL Team (https://arxiv.org/abs/2504.16084)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from typing import List
from collections import Counter
import torch
import numpy as np
from verl.utils.reward_score.ttrl_math import extract_answer, simplify_expression_string, grade
from executor import PythonExecutor
from content_utils import extract_code_block, extract_obj
from utils import load_jsonl
import random

def select_top_k_per_prompt(data, n_votes_per_prompt, n_samples_per_prompt):
    """
    Select the first k rollouts per prompt, used for TTRL downsampling.
    """
    assert len(data) % n_votes_per_prompt == 0, "data length must be divisible by n_votes_per_prompt"
    num_prompts = len(data) // n_votes_per_prompt
    assert n_samples_per_prompt <= n_votes_per_prompt, "n_samples_per_prompt shoud be less than n_votes"
    selected_indices = []
    for i in range(num_prompts):
        start = i * n_votes_per_prompt
        selected_indices.extend(range(start, start + n_samples_per_prompt))

    return data[selected_indices]

def select_top_k_per_prompt_result(batch, n_votes_per_prompt, n_samples_per_prompt):
    assert n_samples_per_prompt <= n_votes_per_prompt
    num_prompts = len(batch)

    for i in range(num_prompts):
        data_item = batch[i]

        obj_ls = data_item.non_tensor_batch["extra_info"]["solved_objective"]
        sol_ls = data_item.non_tensor_batch["extra_info"]["solution"]
        code_ls = data_item.non_tensor_batch["extra_info"]["code_exec_res"]

        assert len(obj_ls) == n_votes_per_prompt, f"prompt {i}: obj len={len(obj_ls)}"
        assert len(sol_ls) == n_votes_per_prompt, f"prompt {i}: sol len={len(sol_ls)}"
        assert len(code_ls) == n_votes_per_prompt, f"prompt {i}: code len={len(code_ls)}"

        data_item.non_tensor_batch["extra_info"]["solved_objective"] = obj_ls[:n_samples_per_prompt]
        data_item.non_tensor_batch["extra_info"]["solution"] = sol_ls[:n_samples_per_prompt]
        data_item.non_tensor_batch["extra_info"]["code_exec_res"] = code_ls[:n_samples_per_prompt]

    return batch
# === Ground Truth Manipulation ===


def apply_original_gt(batch):
    """
    Apply the original ground truth to the batch.
    """
    for i in range(len(batch)):
        data_item = batch[i]
        original_gt = data_item.non_tensor_batch["reward_model"]["original_gt"]
        data_item.non_tensor_batch["reward_model"]["ground_truth"] = original_gt

    return batch

#warning always do this before apply original_gt
def apply_ttrl_gt(batch, gen_batch_output, n, tokenizer):
    """
    Apply the majority vote ground truth to the batch.
    get the results and vote
    """
    assert len(gen_batch_output) % n == 0, "gen_batch_output length must be divisible by n"
    num_prompts = len(gen_batch_output) // n
    assert len(batch) == num_prompts, "batch length must be equal to the number of prompts"

    model_outputs = []  
    ##TODO check reward model with qids;
    # qids_to_resp = {}
    # for i in range(num_prompts):
    #     qid = data_item.non_tensor_batch["extra_info"]["qid"]
    #     data_item = gen_batch_output[i]
    #     response = data_item.batch["prompts"]
    #     prompt_ids = data_item.batch["prompts"]
    #     prompt_length = prompt_ids.shape[-1]
    #     response_ids = data_item.batch["responses"]
    #     valid_response_length = data_item.batch["attention_mask"][prompt_length:].sum()
    #     valid_response_ids = response_ids[:valid_response_length]
    #     response_str = tokenizer.decode(valid_response_ids, skip_special_tokens=True)
    #     if qid not in list(qids_to_resp.keys()):
    #         qids_to_resp[qid]=[response_str]
    #     else:
    #         qids_to_resp[qid].appex wnd(response_str)
    for i in range(num_prompts):
        start = i * n
        for j in range(n):
            data_item = gen_batch_output[start + j] #gen_batch is flat;
            prompt_ids = data_item.batch["prompts"]
            prompt_length = prompt_ids.shape[-1]
            response_ids = data_item.batch["responses"]
            valid_response_length = data_item.batch["attention_mask"][prompt_length:].sum()
            valid_response_ids = response_ids[:valid_response_length]
            response_str = tokenizer.decode(valid_response_ids, skip_special_tokens=True)
            model_outputs.append(response_str)
    # batch get three things zr
    batch_obj, batch_sol, batch_report = get_solver_feedback(model_outputs)#list str #from every response
    ##vote for objective majority
    majority_gt_list, majority_ratio_list = _batch_majority_vote(batch_obj, n)
    
    assert len(batch) == len(majority_gt_list), "batch length must be equal to the number of model outputs"
    
    for i in range(num_prompts):##broadcast
        data_item = batch[i]
        original_gt = data_item.non_tensor_batch["reward_model"]["ground_truth"]
        data_item.non_tensor_batch["reward_model"]["ground_truth"] = majority_gt_list[i]
        data_item.non_tensor_batch["reward_model"]["majority_gt"] = majority_gt_list[i]
        data_item.non_tensor_batch["reward_model"]["original_gt"] = original_gt
        start = i * n
        end = start + n
        
        data_item.non_tensor_batch["extra_info"]["solved_objective"] = batch_obj[start:end]
        data_item.non_tensor_batch["extra_info"]["solution"] = batch_sol[start:end]
        data_item.non_tensor_batch["extra_info"]["code_exec_res"] = batch_report[start:end]
        
    batch.non_tensor_batch["majority_ratio_list"] = np.array(majority_ratio_list, dtype=float)
    return batch


def _batch_majority_vote(model_outputs: List[str], n: int) -> tuple[List[str], List[float]]:
    """
    Used to generate the ground truth for TTRL.
    Input:
        model_outputs: list of str
        n: int
    Output:
        majority_gt_list: list of str
        majority_ratio_list: list of float
    """
    majority_gt_list = []
    majority_ratio_list = []
    assert len(model_outputs) % n == 0
    n_prompts = len(model_outputs) // n
    for i in range(n_prompts):
        prompt_outputs = model_outputs[i * n:(i + 1) * n]
        prompt_majority_gt, prompt_majority_ratio = _majority_vote(prompt_outputs)
        majority_gt_list.append(prompt_majority_gt)
        majority_ratio_list.append(prompt_majority_ratio)
        
    return majority_gt_list, majority_ratio_list


def _majority_vote(model_outputs: List[str]) -> tuple[str, float]:
    assert len(model_outputs) > 0
    # model_answers = [extract_answer(generated_text) for generated_text in model_outputs] ##no need zr
    model_answers = model_outputs
    model_answers = [answer for answer in model_answers if answer is not None]
    model_answers = [simplify_expression_string(answer) for answer in model_answers]
    if len(model_answers) == 0:
        return "None", 0.0
    
    counter = Counter(model_answers)
    
    majority_answer, majority_count = counter.most_common(1)[0]
    majority_ratio = majority_count / len(model_outputs)
    # print(f"DEBUG majority vote {model_answers}")
    # print(f"DEBUG ratio {majority_ratio} , maj ans {majority_answer}")
    return majority_answer, majority_ratio


# === Metrics Computation ===


def compute_ttrl_metrics(batch, n):
    """
    Compute the TTRL metrics.
    """
    assert len(batch) % n == 0, "batch length must be divisible by n"
    num_prompts = len(batch) // n

    # Sort the batch by the ID
    idx = sorted(range(len(batch)), key=lambda x: batch[x].non_tensor_batch["extra_info"]["index"])

    majority_reward = []
    gt_reward = []
    majority_label = []
    gt_label = []

    for i in range(len(batch)):
        data_item = batch[idx[i]]
        majority_reward.append(data_item.batch["token_level_scores"].sum().item())
        gt_reward.append(data_item.batch["token_level_scores_original"].sum().item())
        majority_label.append(str(data_item.non_tensor_batch["reward_model"]["majority_gt"]))##zr integrate with follow grade function(req str)
        gt_label.append(str(data_item.non_tensor_batch["reward_model"]["original_gt"]))##zr integrate with follow grade function(req str)

    ttrl_metrics = _batch_compute_ttrl_metrics(majority_reward, gt_reward, majority_label, gt_label, n=n)
    majority_ratio_list = batch.non_tensor_batch["majority_ratio_list"]
    majority_ratio = sum(majority_ratio_list) / len(majority_ratio_list)
    ttrl_metrics["majority_ratio"] = majority_ratio

    return ttrl_metrics


def _batch_compute_ttrl_metrics(
    majority_reward: List[float],
    gt_reward: List[float],
    majority_label: List[str],
    gt_label: List[str],
    n: int,
):
    """
    Compute the TTRL metrics for batch inputs.
    """
    assert len(majority_reward) == len(gt_reward) == len(majority_label) == len(gt_label)
    assert len(majority_reward) % n == 0
    n_prompts = len(majority_reward) // n
    ttrl_metrics = []
    for i in range(n_prompts):
        prompt_majority_reward = majority_reward[i * n:(i + 1) * n]
        prompt_gt_reward = gt_reward[i * n:(i + 1) * n]
        prompt_majority_label = majority_label[i * n:(i + 1) * n]
        prompt_gt_label = gt_label[i * n:(i + 1) * n]

        assert Counter(prompt_majority_label).most_common(1)[0][1] == n
        assert Counter(prompt_gt_label).most_common(1)[0][1] == n

        prompt_majority_label = prompt_majority_label[0]
        prompt_gt_label = prompt_gt_label[0]

        ttrl_metric = _prompt_compute_ttrl_metrics(prompt_majority_reward, prompt_gt_reward, prompt_majority_label, prompt_gt_label)
        ttrl_metrics.append(ttrl_metric)

    # Compute the average metrics
    ttrl_metrics = {k: sum(d[k] for d in ttrl_metrics) / len(ttrl_metrics) for k in ttrl_metrics[0]}

    return ttrl_metrics

def _prompt_compute_ttrl_metrics(
    majority_reward: List[float],
    gt_reward: List[float],
    majority_label: str,
    gt_label: str,
    ):    
    assert len(majority_reward) == len(gt_reward)

    hit_rate = 1.0 if grade(majority_label, gt_label) else 0.0    
    rewards_hit_rate = 0
    for estimate_reward, true_reward in zip(majority_reward, gt_reward):
        if estimate_reward == true_reward:
            rewards_hit_rate += 1
    rewards_hit_rate = rewards_hit_rate / len(majority_reward)
    
    ttrl_metric = {
        "label_accuracy": hit_rate,
        "reward_accuracy": rewards_hit_rate,
        "majority_voting_reward": sum(majority_reward) / len(majority_reward),
        "ground_truth_reward": sum(gt_reward) / len(gt_reward),
        f"pass@{len(majority_reward)}": 1.0 if sum(gt_reward) >= 1 else 0.0,
    }
    return ttrl_metric


def get_solver_feedback(solution_strs:list[str]):
    """
    given solution strs, get feedback and store in batches
    input: solution strs
    code execution has three results:
    obj_result: number
    solution: ...
    code_excu_result: exec code
    return: obj_result,solution,code_excu_result
    """
    # print(f"DEBUG: sol strs:{solution_strs[0]}")
    # print(f"DEBUG: sol strs:{type(solution_strs)}")
    # print(f"DEBUG: sol strs:{type([extract_code_block(solution_str, 'gurobi') for solution_str in solution_strs])}")
    # print(f"DEBUG: code snippet:{[extract_code_block(solution_str, 'gurobi') for solution_str in solution_strs][0]}")
    executor = PythonExecutor()
    ## randomly pick some lp file in training
    # response = executor.batch_apply([extract_code_block(solution_str, 'gurobi') for solution_str in solution_strs])
    

    dump_lp_prob = 0.0001
    def maybe_append_lp(code: str, idx: int) -> str:
        if not code:
            return code
        if random.random() < dump_lp_prob:
            lp_dir = "/DATA/disk2/zhurui/TTRL/lpdebug"
            return code + f'\nmodel.write("{lp_dir}/debug_{idx}.lp")\n'
        return code

    response = executor.batch_apply([
        maybe_append_lp(extract_code_block(solution_str, 'gurobi'), i)
        for i, solution_str in enumerate(solution_strs)
    ])
    obj_result =[response[0][i] for i in range(len(solution_strs))]
    sol_result = [response[1][i] for i in range(len(solution_strs))]
    code_excu_result = [response[2][i] for i in range(len(solution_strs))]
    
    return obj_result, sol_result, code_excu_result