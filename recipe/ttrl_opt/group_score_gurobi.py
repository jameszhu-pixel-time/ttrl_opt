# https://github.com/volcengine/verl/blob/main/verl/utils/reward_score/math_batch.py
"""
The Stage-1 reward function is based on three criteria: format correctness, execution success, and objective function verification.
"""


import re
import numpy as np
import requests
import json
from collections import Counter
from executor import PythonExecutor
from content_utils import extract_code_block, extract_obj
from utils import load_jsonl
import random
# url = "http://10.200.250.35:8000/execute"

def code_reward(code_excu_result):
    return code_excu_result=='Done'

def safe_to_float(x):
    if x is None:
        return None
    if isinstance(x, (int, float, np.integer, np.floating)):
        return float(x)
    if isinstance(x, str):
        x = x.strip()
        if x == "" or x.lower() == "none":
            return None
        try:
            return float(x)
        except ValueError:
            return None
    return None

def answer_reward(solver_result, ans, code_excu_result, cri=1e-6):
    pred = safe_to_float(solver_result)
    gt = safe_to_float(ans)

    if code_excu_result != "Done":
        return False
    if pred is None or gt is None:
        return False

    rel_err = abs(pred - gt) / (abs(gt) + 1.0)
    return rel_err < cri

# 代码权重最高
def format_reward(processed_str: str, order:bool=False) -> bool:
    minus_score = 0

    tags = {
        'think_start':('<think>', 1),
        'think_end': ('</think>', 1),
        'model_start': ('<model', 1),
        'model_end': ('</model>', 1),
        'python_start': ('<python>', 1),
        'python_end': ('</python>', 1)
    }

    position = {}
    for tag_name, (tag_str, expected_count) in tags.items():
        count = processed_str.count(tag_str)
        position[tag_name] = pos = processed_str.find(tag_str)

        if count != expected_count:
            if "python" not in tag_name:
                minus_score += 1/8
            else:
                minus_score += 1/4
                
    # Verify tag order
    order_set = [
    position['think_start'], position['think_end'],
    position['model_start'], position['model_end'],
    position['python_start'], position['python_end']
]

    if order_set[1] > min(order_set[2:5]):
        minus_score += 1/3

    flag = 0
    for i in range(0, 6, 2):
        if order_set[i] > order_set[i + 1]:
            flag = 1
            break
    if flag == 1:
        minus_score += 1/3

    if order_set[4] <= max(order_set[:4]):
        minus_score += 1/3

    return 2 - minus_score

# by Batch   solution_str, (all rollout response lists)
def compute_score_simplified(data_sources, solution_strs, ground_truths, extra_infos):
    order = False
    format_score = 0.5
    ans_score = 1.0
    code_score = 1.0

    # TTRL cached path: extra_infos[i] 里现在应当是 rollout-level 单值
    if extra_infos[0].get("code_exec_res", None) is not None:
        print("[DEBUG] ttrl compute")
        print("[DEBUG] extra_infos[0].keys() =", list(extra_infos[0].keys()))
        print(type(extra_infos[0]["solved_objective"]), extra_infos[0]["solved_objective"])
        print(type(extra_infos[0]["code_exec_res"]), extra_infos[0]["code_exec_res"])
        obj_result = [extra_infos[i]["solved_objective"] for i in range(len(solution_strs))]
        sol_result = [extra_infos[i]["solution"] for i in range(len(solution_strs))]
        code_excu_result = [extra_infos[i]["code_exec_res"] for i in range(len(solution_strs))]

        print(f"[DEBUG] length check: obj={len(obj_result)}, sol={len(sol_result)}, code={len(code_excu_result)}")

    else:
        print("[DEBUG] original compute")
        return compute_score(data_sources, solution_strs, ground_truths, extra_infos)

    assert len(solution_strs) == len(ground_truths), (len(solution_strs), len(ground_truths))
    assert len(obj_result) == len(solution_strs), (len(obj_result), len(solution_strs))
    assert len(sol_result) == len(solution_strs), (len(sol_result), len(solution_strs))
    assert len(code_excu_result) == len(solution_strs), (len(code_excu_result), len(solution_strs))

    format_ = [format_reward(solution_strs[i], order) for i in range(len(solution_strs))]
    code_ = [code_reward(code_excu_result[i]) for i in range(len(solution_strs))]
    ans = [answer_reward(obj_result[i], ground_truths[i], code_excu_result[i]) for i in range(len(solution_strs))]

    rewards = [
        ans[i] * ans_score + format_[i] * format_score + code_[i] * code_score
        for i in range(len(solution_strs))
    ]

    for i in range(len(solution_strs)):
        do_print = random.randint(1, 2048) == 1
        if do_print:
            print(f"[DEBUG] reward={rewards[i]}")
            print(f"[DEBUG] obj={obj_result[i]}, sol={sol_result[i]}, code={code_excu_result[i]}, gt={ground_truths[i]}")
            print(f"[DEBUG] format={format_[i]}, code_reward={code_[i]}, ans={ans[i]}")
            print(f"code snippet: {extract_code_block(solution_strs[i], 'gurobi')}")

    return rewards

def compute_score(data_sources, solution_strs, ground_truths, extra_infos):
    order = False
    format_score = 0.5
    ans_score = 1.
    # sol_score = 2.
    code_score = 1.
    executor = PythonExecutor()
    ##testing;
    
    response = executor.batch_apply([extract_code_block(solution_str, 'gurobi') for solution_str in solution_strs])
    
    obj_result =[response[0][i] for i in range(len(solution_strs))]
    code_excu_result = [response[2][i] for i in range(len(solution_strs))]
    """
    # sol_result = [response[1][i] for i in range(len(solution_strs))]
    # if 'sol' in extra_infos[0]:
    #     sol = [sol_reward(extra_infos[i]['sol'], sol_result[i]) for i in range(len(ground_truths))]
    # else:
    #     sol = [0 for i in range(len(ground_truths))]
    """
    format_ = [format_reward(solution_strs[i], order) for i in range(len(solution_strs))]
    code_ = [code_reward(code_excu_result[i]) for i in range(len(code_excu_result))]
    ans = [answer_reward(obj_result[i], ground_truths[i], code_excu_result[i]) for i in range(len(ground_truths))]
    rewards = [ans[i] * ans_score + format_[i] * format_score + code_[i] * code_score for i in range(len(ans))]
    for i in range(len(solution_strs)):
        do_print = random.randint(1, 2048) == 1
        if do_print:
            print(f"[DEBUG]: solution results sampled {solution_strs[i]}")
            print(f"[DEBUG]: reward results sampled {rewards[i]}")
            print(f"code snippet{extract_code_block(solution_strs[i], 'gurobi')}")
            print(f"""[DEBUG]: detailed feedback sampled :
                code results:{code_excu_result[i]},
                obj_result results:{obj_result[i]},
                format: {format_[i]},
                code: {code_[i]},
                ans: {ans[i]},
                ground_truth:{ground_truths[i]}
                """)
    return rewards

