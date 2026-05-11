import os
import json
from pathlib import Path
from scr.knowledge_graph.llm_client import call_kg_llm, load_env_file

def debug_llm_chat():
    # 1. 加载配置
    project_root = Path(__file__).resolve().parent
    env_file = project_root / ".env"
    print(f"[*] 加载环境配置: {env_file}")
    load_env_file(env_file)

    model_name = os.environ.get("KG_LLM_MODEL")
    api_url = os.environ.get("KG_LLM_API_URL")
    
    print(f"[*] 使用模型: {model_name}")
    print(f"[*] API 地址: {api_url}")

    # 2. 发送一个简单的聊天测试
    test_prompt = "你好，请简单介绍一下你自己。并返回一个简单的 JSON 格式，包含字段 'status': 'ok'。"
    
    print("\n[*] 发送测试 Prompt: ", test_prompt)
    print("-" * 30)
    
    try:
        response = call_kg_llm(test_prompt, verbose=True)
        print("\n[+] LLM 原始响应内容:")
        print(response)
        print("-" * 30)
        
        # 尝试检查是否包含 JSON
        if "{" in response and "}" in response:
            print("[*] 检测到响应中可能包含 JSON 内容。")
        else:
            print("[!] 响应中似乎不包含 JSON。")
            
    except Exception as e:
        print(f"\n[-] LLM 调用失败!")
        print(f"[-] 错误信息: {e}")

if __name__ == "__main__":
    debug_llm_chat()
