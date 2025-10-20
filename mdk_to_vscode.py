# -*- coding: utf-8 -*-
import os
import xml.etree.ElementTree as ET
import json
import re
import argparse
from pathlib import Path
import logging

# ====== 全局可配置项 ======
# 修改此处即可更换编译器路径
COMPILER_PATH = "C:/Users/25799/Documents/gcc-arm-none-eabi-10.3-2021.10/bin/arm-none-eabi-gcc.exe"
# =========================

# .editorconfig 文件的标准内容
EDITORCONFIG_CONTENT = """# EditorConfig is awesome: https://EditorConfig.org

# top-most EditorConfig file
root = true

[*]
indent_style = space
indent_size = 4
end_of_line = crlf
trim_trailing_whitespace = true
insert_final_newline = true
"""

# 日志初始化（可根据需要调整级别和格式）
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)

# 错误处理和日志输出的辅助函数

def log_info(msg: str) -> None:
    logging.info(msg)

def log_warning(msg: str) -> None:
    logging.warning(msg)

def log_error(msg: str) -> None:
    logging.error(msg)

def safe_read_json(path: str) -> dict:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        log_error(f"读取 JSON 文件失败: {e}")
        return {}

def safe_write_json(path: str, data: dict) -> None:
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        log_info(f"成功写入 JSON 文件: {path}")
    except Exception as e:
        log_error(f"写入 JSON 文件失败: {e}")

def generate_vscode_config_from_file(input_filepath, config_name):
    """
    从 Keil .uvprojx 文件读取配置，返回提取到的 includePath 和 defines。

    参数:
    input_filepath (str): 输入的 .uvprojx 文件路径。
    config_name (str): 用于配置中的名称（现在仅作日志记录）。

    返回:
    dict: 包含 'includePath' 和 'defines' 列表的字典，如果失败则返回 None。
    """

    def normalize_and_clean_path(path):
        """将路径中的 Windows 分隔符 \\ 替换为 /，并移除开头的 '../'"""
        # 1. 统一分隔符
        path = path.replace('\\', '/')
        # 2. 移除开头的 '../' 前缀
        while path.startswith('../'):
            path = path[3:] # 秼除前三个字符 "../"
        return path

    try:
        # 尝试使用 Keil 项目常用的 'gbk' 编码打开文件，以避免解析错误
        # ET.parse 并不直接支持 encoding 参数，但可以通过 io.open/ET.fromstring 组合来实现，
        # 不过为了简洁和与现有代码结构兼容，我们保持 ET.parse()，并依赖其内部的编码猜测，
        # 仅修复警告部分。
        tree = ET.parse(input_filepath)
        root = tree.getroot()

        cads_node = root.find('.//Cads')

        # *** 修复 DeprecationWarning: 使用 'is None' 显式检查节点是否存在 ***
        if cads_node is None:
            # 原本这里是被注释掉的，现在修复了布尔检查逻辑
            # print(f"错误: 在文件 '{input_filepath}' 中未找到 <Cads> 节点。")
            return None

        extracted_data = {
            "includePath": [],
            "defines": []
        }

        # 提取 <IncludePath> 配置
        path_node = cads_node.find('.//VariousControls/IncludePath')
        # if path_node is not None and path_node.text: 保持不变，这是正确的检查方式
        if path_node is not None and path_node.text:
            paths = [
                normalize_and_clean_path(p.strip())
                for p in path_node.text.split(';')
                if p.strip()
            ]
            extracted_data['includePath'] = paths

        # 提取 <Define> 配置
        define_node = cads_node.find('.//VariousControls/Define')
        # if define_node is not None and define_node.text: 保持不变
        if define_node is not None and define_node.text:
            defines = [d.strip() for d in define_node.text.split(',') if d.strip()]
            extracted_data['defines'] = defines

        return extracted_data

    except FileNotFoundError:
        print(f"错误: 文件 '{input_filepath}' 不存在。")
        return None
    except ET.ParseError as e:
        print(f"错误: XML 解析失败 - {e}")
        return None
    except Exception as e:
        print(f"发生未知错误: {e}")
        return None


def ensure_vscode_c_cpp_properties(path, create_default=True):
    """Ensure the .vscode/c_cpp_properties.json exists and return its path.

    If create_default is False, create the file with an empty configurations list
    instead of a Default configuration.
    """
    vscode_dir = Path(path)
    vscode_dir.mkdir(parents=True, exist_ok=True)
    c_cpp_path = vscode_dir / 'c_cpp_properties.json'
    if not c_cpp_path.exists():
        if create_default:
            configurations = [
                {
                    "name": "Default",
                    "intelliSenseMode": "linux-gcc-arm",
                    "compilerPath": COMPILER_PATH,
                    "cStandard": "c99",
                    "cppStandard": "c++11",
                    "includePath": [],
                    "defines": []
                }
            ]
        else:
            configurations = []

        template = {
            "configurations": configurations,
            "version": 4
        }
        with open(c_cpp_path, 'w', encoding='utf-8') as f:
            json.dump(template, f, indent=4, ensure_ascii=False)
    return str(c_cpp_path)


def update_c_cpp_properties(new_data, output_filepath, config_name):
    """
    读取现有的 c_cpp_properties.json 文件，更新（或创建）指定配置下的
    includePath 和 defines 字段，并写回文件。
    """

    if not os.path.exists(output_filepath):
        print(f"错误: 文件 '{output_filepath}' 不存在。请先手动创建一个基础配置的 JSON 文件。")
        return

    try:
        # 1. 读取现有文件内容 (JSON文件通常使用UTF-8，保持不变)
        with open(output_filepath, 'r', encoding='utf-8') as f:
            content = json.load(f)

        # 2. 确保 configurations 列表存在
        if 'configurations' not in content or not isinstance(content['configurations'], list):
            print("警告: 现有的 c_cpp_properties.json 缺少 'configurations' 列表，无法更新。")
            return

        # 3. 查找或创建目标配置
        target_config = None
        for config in content['configurations']:
            if config.get('name') == config_name:
                target_config = config
                break

        # 如果找不到指定名称的配置，则创建一个新的基础配置
        if target_config is None:
            print(f"警告: 未找到名称为 '{config_name}' 的配置，将创建一个新的基础配置。")
            target_config = {
                "name": config_name,
                "intelliSenseMode": "linux-gcc-arm",
                "compilerPath": "arm-none-eabi-gcc",
                "cStandard": "c99",
                "cppStandard": "c++11"
            }
            content['configurations'].append(target_config)

        # 4. 清空并添加新的 includePath 和 defines
        target_config['includePath'] = new_data.get('includePath', [])
        target_config['defines'] = new_data.get('defines', [])

        # 5. 写回文件
        with open(output_filepath, 'w', encoding='utf-8') as f:
            json.dump(content, f, indent=4, ensure_ascii=False)

        print(f"成功更新 c_cpp_properties.json 中配置 '{config_name}' 的 includePath 和 defines。")

    except json.JSONDecodeError:
        print(f"错误: 文件 '{output_filepath}' JSON 格式不正确。请检查文件内容。")
    except Exception as e:
        print(f"更新文件时发生未知错误: {e}")


def write_editorconfig_file(output_dir):
    """
    在指定目录下生成 .editorconfig 文件。
    """
    editorconfig_path = os.path.join(output_dir, '.editorconfig')

    try:
        if os.path.exists(editorconfig_path):
            print(f"文件 '{editorconfig_path}' 已存在，跳过生成。")
            return

        # .editorconfig 应该使用 UTF-8 编码
        with open(editorconfig_path, 'w', encoding='utf-8') as f:
            f.write(EDITORCONFIG_CONTENT)

        print(f"成功生成文件: {editorconfig_path}")

    except Exception as e:
        print(f"生成 .editorconfig 文件时发生错误: {e}")


def find_uvprojx_files(start_dir):
    """
    遍历目录及子目录，寻找所有以 '.uvprojx' 为后缀的文件。
    """
    uvprojx_files = []
    for root, dirs, files in os.walk(start_dir):
        for file in files:
            if file.endswith('.uvprojx'):
                uvprojx_files.append(os.path.join(root, file))
    return uvprojx_files


def find_first_uvprojx(src_dir: str) -> str | None:
    files = find_uvprojx_files(src_dir)
    if not files:
        log_warning(f"在目录 '{src_dir}' 未找到任何 .uvprojx 文件。")
        return None
    return files[0]


def parse_keil_config(uvprojx_path: str, config_name: str) -> dict | None:
    data = generate_vscode_config_from_file(uvprojx_path, config_name)
    if not data:
        log_error(f"解析 Keil 工程文件失败: {uvprojx_path}")
        return None
    return data


def ensure_vscode_config(vscode_dir: str, create_default: bool) -> str:
    return ensure_vscode_c_cpp_properties(vscode_dir, create_default=create_default)


def update_vscode_config(data: dict, config_path: str, config_name: str) -> None:
    update_c_cpp_properties(data, config_path, config_name)


def main():
    """
    主流程伪代码化：
    1. 查找 Keil 工程文件
    2. 解析配置
    3. 生成/更新 VSCode 配置
    """
    parser = argparse.ArgumentParser(
        description='从 Keil .uvprojx 生成或更新 VSCode c_cpp_properties.json',
        formatter_class=argparse.RawTextHelpFormatter
    )
    script_dir = Path(__file__).parent.resolve()
    parser.add_argument('--src-dir', '-s', type=str, default=str(script_dir), help='搜索 .uvprojx 的起始目录。')
    parser.add_argument('--vscode-dir', '-v', type=str, default=str(script_dir / '.vscode'), help='目标 .vscode 目录。')
    parser.add_argument('--create-editorconfig', action='store_true', help='如果不存在，则在源目录创建 .editorconfig 文件。')
    parser.add_argument('--config-name', help='指定生成的配置名称。')
    parser.add_argument('--create-default-config', action='store_true', help='如果 c_cpp_properties.json 不存在，是否创建一个 "Default" 配置节。')
    args = parser.parse_args()

    if args.create_editorconfig:
        write_editorconfig_file(args.src_dir)

    uvprojx_path = find_first_uvprojx(args.src_dir)
    if not uvprojx_path:
        return
    config_name = args.config_name or Path(uvprojx_path).stem
    log_info(f"解析文件: {uvprojx_path}")
    log_info(f"目标配置名称: {config_name}")

    data = parse_keil_config(uvprojx_path, config_name)
    if not data:
        return
    vscode_dir = args.vscode_dir
    Path(vscode_dir).mkdir(exist_ok=True)
    config_path = ensure_vscode_config(vscode_dir, args.create_default_config)
    update_vscode_config(data, config_path, config_name)
    log_info("全部流程完成！")

# --- 主程序入口 ---
if __name__ == "__main__":
    main()
