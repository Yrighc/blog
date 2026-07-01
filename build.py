#!/usr/bin/env python3
import os
import re
import shutil
import sys
import datetime
import subprocess

VAULT_DIR = "public"
HUGO_DIR = "hugo-site"
HUGO_CONTENT_DIR = os.path.join(HUGO_DIR, "content")
HUGO_STATIC_DIR = os.path.join(HUGO_DIR, "static", "resources")

# 全局存储所有已存在的公开笔记文件名（全小写，不带后缀）
EXISTING_PAGES = set()

def scan_existing_pages():
    global EXISTING_PAGES
    EXISTING_PAGES.clear()
    if not os.path.exists(VAULT_DIR):
        return
        
    for root, dirs, files in os.walk(VAULT_DIR):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for file in files:
            if file.endswith('.md'):
                name_without_ext = os.path.splitext(file)[0].lower()
                EXISTING_PAGES.add(name_without_ext)

def setup_dirs():
    if os.path.exists(HUGO_CONTENT_DIR):
        shutil.rmtree(HUGO_CONTENT_DIR)
    os.makedirs(HUGO_CONTENT_DIR, exist_ok=True)

    if os.path.exists(HUGO_STATIC_DIR):
        shutil.rmtree(HUGO_STATIC_DIR)
    os.makedirs(HUGO_STATIC_DIR, exist_ok=True)
    
    create_system_pages()

def create_system_pages():
    search_path = os.path.join(HUGO_CONTENT_DIR, "search.md")
    search_content = """---
title: "搜索"
layout: "search"
summary: "search"
placeholder: "搜索笔记..."
---
"""
    with open(search_path, "w", encoding="utf-8") as f:
        f.write(search_content)
        
    archive_path = os.path.join(HUGO_CONTENT_DIR, "archives.md")
    archive_content = """---
title: "归档"
layout: "archives"
url: "/archives"
summary: "archives"
---
"""
    with open(archive_path, "w", encoding="utf-8") as f:
        f.write(archive_content)

def has_yaml_front_matter(content):
    lines = content.splitlines()
    if len(lines) > 0 and lines[0].strip() == '---':
        for i in range(1, len(lines)):
            if lines[i].strip() == '---':
                return True
    return False

def inject_category(content, category_name):
    if not category_name:
        return content
        
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if match:
        yaml_block = match.group(1)
        rest_of_content = content[match.end():]
        
        lines = yaml_block.splitlines()
        has_categories = False
        for line in lines:
            if line.strip().startswith('categories:'):
                has_categories = True
                break
                
        if not has_categories:
            lines.append(f"categories: [\"{category_name}\"]")
            new_yaml = "\n".join(lines)
            return f"---\n{new_yaml}\n---\n{rest_of_content}"
    return content

def add_front_matter(content, filepath, category_name=None):
    if has_yaml_front_matter(content):
        return content
        
    title = os.path.splitext(os.path.basename(filepath))[0]
    mtime = os.path.getmtime(filepath)
    date_str = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%dT%H:%M:%S+08:00')
    
    category_line = f"\ncategories: [\"{category_name}\"]" if category_name else ""
    front_matter = f"---\ntitle: \"{title}\"\ndate: {date_str}{category_line}\ndraft: false\n---\n\n"
    return front_matter + content

def replace_wikilinks(content):
    def img_repl(match):
        img_name = match.group(1).strip()
        return f"![image](/resources/{img_name})"
        
    content = re.sub(r'!\[\[([^\]|]+)(?:\|[^\]]*)?\]\]', img_repl, content)

    def link_repl(match):
        target = match.group(1).strip()
        alias = match.group(2).strip() if match.group(2) else None
        
        # 拆分锚点并适配首页 Index
        if '#' in target:
            page, anchor = target.split('#', 1)
            if page.lower() == 'index':
                page = '_index'
            anchor_slug = anchor.replace(' ', '-').lower()
            ref_path = f"{page}.md#{anchor_slug}"
        else:
            if target.lower() == 'index':
                page = '_index'
                ref_path = "_index.md"
            else:
                page = target
                ref_path = f"{target}.md"
            
        text = alias if alias else target

        # 提取文件名用作已存在性检查 (去路径、去后缀)
        page_filename = os.path.basename(page)
        if page_filename.lower().endswith('.md'):
            page_filename = page_filename[:-3]
        page_key = page_filename.lower()

        # 检查目标页面是否存在（如果指向的是首页，_index.md 始终存在）
        page_exists = (page_key in EXISTING_PAGES) or (page_key == '_index')
        
        if page_exists:
            return f"[{text}]({{{{< ref \"{ref_path}\" >}}}})"
        else:
            # 死链/未创建页面降级为带虚线的灰色纯文本，防止编译报错
            return f"<span class=\"dead-link\" style=\"color: var(--text-muted); border-bottom: 1px dashed var(--text-muted);\">{text}</span>"

    content = re.sub(r'\[\[([^\]|]+)(?:\|([^\]]+))?\]\]', link_repl, content)
    return content

def process_vault():
    if not os.path.exists(VAULT_DIR):
        print(f"Error: Vault 目录 '{VAULT_DIR}' 不存在。")
        sys.exit(1)
        
    for root, dirs, files in os.walk(VAULT_DIR):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        for file in files:
            if file.startswith('.'):
                continue
                
            src_path = os.path.join(root, file)
            ext = os.path.splitext(file)[1].lower()
            
            if ext == '.md':
                rel_path = os.path.relpath(src_path, VAULT_DIR)
                
                parts = rel_path.split(os.sep)
                category_name = parts[0] if len(parts) > 1 else None
                if category_name and category_name.lower() in ['resources', 'static']:
                    category_name = None
                
                if os.path.basename(rel_path).lower() == 'index.md':
                    rel_path = os.path.join(os.path.dirname(rel_path), '_index.md')
                
                dest_path = os.path.join(HUGO_CONTENT_DIR, rel_path)
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                
                with open(src_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                content = replace_wikilinks(content)
                if category_name:
                    content = inject_category(content, category_name)
                    
                content = add_front_matter(content, src_path, category_name)
                
                with open(dest_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                    
            elif ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.pdf']:
                dest_path = os.path.join(HUGO_STATIC_DIR, file)
                shutil.copy2(src_path, dest_path)

def main():
    scan_existing_pages() # 👈 首先扫描存在的页面
    setup_dirs()
    process_vault()
    print("✓ Obsidian 笔记兼容性处理完成！")
    
    if len(sys.argv) > 1:
        action = sys.argv[1]
        if action == "--serve":
            print("启动 Hugo 本地服务...")
            subprocess.run(["hugo", "server", "-D"], cwd=HUGO_DIR)
        elif action == "--build":
            print("构建 Hugo 静态文件...")
            subprocess.run(["hugo", "--gc", "--minify"], cwd=HUGO_DIR)
    else:
        print("提示: 可使用 'python3 build.py --serve' 启动预览，或 'python3 build.py --build' 构建静态站。")

if __name__ == "__main__":
    main()
