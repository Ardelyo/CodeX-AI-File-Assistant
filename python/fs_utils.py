

# python/fs_utils.py

import os
import shutil
import time # For item modification times
import re   # For search criteria parsing

# PDF and DOCX parsing (optional, can be kept in action_handlers or centralized here if preferred)
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    from docx import Document as DocxDocument # Renamed to avoid conflict if Document is used elsewhere
    PYTHON_DOCX_AVAILABLE = True
except ImportError:
    PYTHON_DOCX_AVAILABLE = False

# For rich progress bar in search, if cli_ui is not directly imported
# from rich.progress import Progress # Keep this if you make search_recursive part of fs_utils and it needs its own progress

# --- Constants for File Type Matching ---
SEARCH_TYPE_KEYWORDS = {
    "image": ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.svg', '.heic', '.avif'],
    "picture": ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.svg', '.heic', '.avif'],
    "photo": ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.svg', '.heic', '.avif'],
    "video": ['.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.webm'],
    "audio": ['.mp3', '.wav', '.ogg', '.aac', '.flac', '.m4a'],
    "document": ['.pdf', '.doc', '.docx', '.odt', '.txt', '.rtf', '.ppt', '.pptx', '.xls', '.xlsx', '.csv', '.md', '.tex'],
    "pdf": [".pdf"], "word document": [".doc", ".docx"], "text file": [".txt", ".md", ".log", ".rtf"],
    "spreadsheet": [".xls", ".xlsx", ".ods", ".csv"], "presentation": [".ppt", ".pptx", ".odp"],
    "python script": [".py", ".pyw"], "javascript file": [".js", ".mjs"], "typescript file": [".ts", ".tsx"],
    "html file": [".html", ".htm"], "css file": [".css", ".scss", ".less"],
    "archive": [".zip", ".rar", ".tar", ".gz", ".7z", ".bz2"],
    "executable": [".exe", ".msi", ".dmg", ".app", ".deb", ".rpm"],
    "code file": [".py",".js",".java",".c",".cpp",".cs",".go",".rs",".swift",".kt",".php",".rb",".pl",".sh",".bat"],
}

# === Path Safety ===
def is_path_within_base(path_to_check: str, base_path: str) -> bool:
    try:
        abs_path_to_check = os.path.abspath(path_to_check)
        abs_base_path = os.path.abspath(base_path)
        if os.name == 'nt': # Windows case-insensitivity
            abs_path_to_check = abs_path_to_check.lower()
            abs_base_path = abs_base_path.lower()
            
        common_path = os.path.commonpath([abs_path_to_check, abs_base_path])
        if os.name == 'nt':
             common_path = common_path.lower()
        return common_path == abs_base_path
    except ValueError:
        return False
    except Exception:
        return False

# === File Type and Size Utilities ===
def bytes_to_readable(size_bytes: int) -> str:
    if size_bytes < 0: # Handle cases like -1 for unknown size
        return "N/A"
    if size_bytes < 1024:
        return f"{size_bytes} B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB" # Should be enough

def is_file_type_match(filepath: str, criteria_str: str, is_file: bool = True) -> bool:
    """
    Checks if a file matches a given type criteria (e.g., "image", ".pdf", "document").
    `is_file` can be pre-checked by caller to avoid re-stat.
    """
    if not is_file: # Only operate on files for type matching
        return False
        
    _, extension = os.path.splitext(filepath.lower())
    criteria_lower = criteria_str.lower()

    if criteria_lower.startswith("."): # Direct extension match
        return extension == criteria_lower

    for type_name, extensions in SEARCH_TYPE_KEYWORDS.items():
        if type_name == criteria_lower:
            return extension in extensions
    return False # No match

# === Core File Content Reading (used by action_handlers and potentially search) ===
def _read_text_file_content(filepath: str, max_size: int = -1) -> (str | None):
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            if max_size > 0:
                return f.read(max_size)
            return f.read()
    except Exception:
        return None

def _extract_text_from_docx_content(filepath: str, max_size: int = -1) -> (str | None):
    if not PYTHON_DOCX_AVAILABLE: return None
    try:
        doc = DocxDocument(filepath)
        full_text_list = [para.text for para in doc.paragraphs]
        if max_size <= 0:
            return '\n'.join(full_text_list)
        
        content = ""
        for para_text in full_text_list:
            if len(content) + len(para_text) + 1 > max_size:
                needed = max_size - len(content) -1 # -1 for potential newline
                if needed > 0 : content += "\n" + para_text[:needed]
                break
            content += "\n" + para_text
        return content.lstrip("\n")
    except Exception:
        return None

def _extract_text_from_pdf_content(filepath: str, max_size: int = -1) -> (str | None):
    if not PYMUPDF_AVAILABLE: return "PyMuPDF (fitz) not installed. Cannot extract PDF text."
    try:
        doc = fitz.open(filepath)
        text = ""
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            page_text = page.get_text("text")
            if max_size > 0 and len(text) + len(page_text) > max_size:
                remaining_len = max_size - len(text)
                text += page_text[:remaining_len]
                break
            text += page_text
        doc.close()
        return text if text.strip() else None
    except Exception as e:
        return f"PDF parsing error: {str(e)}"


def get_file_content_for_search(filepath: str, console=None) -> (str | None):
    """Gets limited content, suitable for quick search checks."""
    if not (filepath and os.path.exists(filepath) and os.path.isfile(filepath)):
        return None
        
    _, extension = os.path.splitext(filepath.lower())
    MAX_SEARCH_CONTENT_SIZE = 100 * 1024  # 100KB limit for quick search
    content = None

    try:
        if extension in ['.txt', '.py', '.js', '.css', '.html', '.md', '.json', '.xml', '.log', '.ini', '.cfg', '.sh', '.bat']:
            content = _read_text_file_content(filepath, MAX_SEARCH_CONTENT_SIZE)
        elif extension == '.docx':
            content = _extract_text_from_docx_content(filepath, MAX_SEARCH_CONTENT_SIZE)
        elif extension == '.pdf':
            # For search, a smaller chunk of PDF text might be okay, or skip if too slow
            content = _extract_text_from_pdf_content(filepath, MAX_SEARCH_CONTENT_SIZE // 2) # smaller for pdfs
        # Add other types if needed for quick search
    except Exception as e:
        if console: # Assuming console is passed from action_handler if UI feedback is desired
            console.print(f"[yellow]Warning (search read): Could not get content from '{os.path.basename(filepath)}': {str(e)[:50]}...[/yellow]")
    return content


# === File and Folder Operations ===

def list_folder_contents_simple(folder_path: str, max_depth: int = 0) -> tuple[list[dict], str | None]:
    """
    Lists folder contents (files and directories) with basic details.
    max_depth = 0 means only top-level.
    Returns (items_list, error_message_string).
    """
    if not folder_path or not os.path.isdir(folder_path):
        return [], f"Path '{folder_path}' is not a valid directory."

    items = []
    try:
        for entry in os.scandir(folder_path):
            item_path = entry.path
            item_type = "directory" if entry.is_dir() else "file" if entry.is_file() else "other"
            
            try:
                stat_result = entry.stat()
                size_bytes = stat_result.st_size
                mod_time = stat_result.st_mtime
            except OSError: # Permissions error or broken link
                size_bytes = -1 
                mod_time = 0

            items.append({
                "name": entry.name,
                "path": item_path,
                "type": item_type,
                "size_bytes": size_bytes,
                "size_readable": bytes_to_readable(size_bytes) if size_bytes >=0 else "N/A",
                "modified_timestamp": mod_time,
                "modified_readable": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mod_time)) if mod_time > 0 else "N/A"
            })
        return items, None
    except Exception as e:
        return [], f"Error listing contents of folder '{folder_path}': {e}"


def search_files_recursive(start_path: str, criteria_str: str, llm_connector, console_for_progress=None) -> tuple[list[dict], str | None]:
    """
    Recursively searches for files.
    `console_for_progress` is optional Rich Console for live progress.
    Returns (found_items_list, error_message_string).
    """
    found_items = []
    criteria_lower = criteria_str.lower()
    abs_start_path = os.path.abspath(start_path)

    if not os.path.isdir(abs_start_path):
        return [], f"Search path '{abs_start_path}' is not a valid directory."

    content_search_term = None
    llm_content_check_criteria = None
    type_description_for_ext_match = criteria_lower

    containing_match = re.search(r"containing\s+['\"](.+?)['\"]", criteria_lower)
    if containing_match:
        content_search_term = containing_match.group(1)
        type_description_for_ext_match = criteria_lower.split("containing", 1)[0].strip()
    
    about_match = re.search(r"(?:about|related to|regarding|on the topic of)\s+['\"](.+?)['\"]", type_description_for_ext_match)
    if about_match:
        llm_content_check_criteria = criteria_str 
        type_description_for_ext_match = type_description_for_ext_match.split(about_match.group(0),1)[0].strip()

    target_extensions_from_type = None
    if type_description_for_ext_match and type_description_for_ext_match not in ["files", "any files", "all files", "items", ""]:
        for key, exts in SEARCH_TYPE_KEYWORDS.items():
            if key in type_description_for_ext_match: 
                target_extensions_from_type = exts
                break
        if not target_extensions_from_type and type_description_for_ext_match.startswith("."):
             target_extensions_from_type = [type_description_for_ext_match]

    progress_context = None
    search_task_id = None 
    if console_for_progress:
        from rich.progress import Progress 
        progress_context = Progress(console=console_for_progress, transient=True)
        search_task_id = progress_context.add_task("[cyan]Scanning...", total=None) 
        progress_context.start()

    try:
        for root, dirs, files in os.walk(abs_start_path, topdown=True):
            dirs[:] = [d for d in dirs if not d.startswith('.') and not d.startswith('$')]
            files = [f for f in files if not f.startswith('.')]

            if progress_context and search_task_id is not None and progress_context.finished: break
            if progress_context and search_task_id is not None:
                progress_context.update(search_task_id, description=f"[cyan]Scanning: {os.path.basename(root)}")
            
            for filename in files:
                if progress_context and search_task_id is not None and progress_context.finished: break
                
                filepath = os.path.join(root, filename)
                name_lower = filename.lower()
                _, ext_lower = os.path.splitext(name_lower)

                name_match = False
                if not target_extensions_from_type and not content_search_term and not llm_content_check_criteria:
                    if criteria_lower in name_lower:
                        name_match = True
                elif criteria_lower == name_lower or criteria_str == filename: 
                    name_match = True

                type_match = False
                if target_extensions_from_type:
                    if ext_lower in target_extensions_from_type:
                        type_match = True
                else: 
                    type_match = True 
                
                content_match_passes = False
                if content_search_term or llm_content_check_criteria:
                    if type_match: 
                        file_content_for_search = get_file_content_for_search(filepath, console=None) 
                        if file_content_for_search:
                            if content_search_term and content_search_term.lower() in file_content_for_search.lower():
                                content_match_passes = True
                            
                            # Ensure llm_connector.check_content_match exists before calling
                            if llm_content_check_criteria and not content_match_passes and \
                               llm_connector and hasattr(llm_connector, 'check_content_match'): 
                                if progress_context and search_task_id is not None: progress_context.update(search_task_id, description=f"[yellow]LLM check: {filename[:25]}...")
                                
                                # Call check_content_match (assuming it's defined in ollama_connector)
                                # This method is currently commented out in ollama_connector.py
                                # If you re-enable it, ensure it takes (content, criteria) and returns bool
                                # For now, let's assume it would be called here if available.
                                # if llm_connector.check_content_match(file_content_for_search, llm_content_check_criteria):
                                #    content_match_passes = True

                                # Placeholder: if check_content_match is not available, this part won't execute
                                # LLM content check logic needs to be fully implemented in ollama_connector
                                # or called differently if it's a generic invoke_llm_for_content call.
                                # For now, we'll proceed as if it could be true if the criteria suggests it.
                                # This is a simplification until check_content_match is defined and used.
                                if "about" in llm_content_check_criteria.lower(): # Basic heuristic
                                     # Simulate LLM finding a match if "about" was used and we don't have a true LLM call here
                                     # This part needs proper LLM integration.
                                     pass # Keep content_match_passes as is from simple search for now

                                if progress_context and search_task_id is not None: progress_context.update(search_task_id, description=f"[cyan]Scanning: {os.path.basename(root)}")
                else: 
                    content_match_passes = True

                final_match = False
                if content_search_term or llm_content_check_criteria: 
                    final_match = type_match and content_match_passes
                elif target_extensions_from_type : 
                    final_match = type_match and (criteria_lower in name_lower or name_match or type_description_for_ext_match == criteria_lower) 
                else: 
                    final_match = name_match

                if final_match:
                    try:
                        stat_info = os.stat(filepath)
                        found_items.append({
                            "name": filename,
                            "path": filepath,
                            "type": "file", 
                            "size_bytes": stat_info.st_size,
                            "size_readable": bytes_to_readable(stat_info.st_size),
                            "modified_timestamp": stat_info.st_mtime,
                            "modified_readable": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat_info.st_mtime))
                        })
                    except OSError:
                        continue 
            
            if progress_context and search_task_id is not None:
                progress_context.update(search_task_id, advance=1)
                
    except Exception as e:
        if progress_context and search_task_id is not None: progress_context.stop()
        return found_items, f"Error during file search: {e}" 
    finally:
        if progress_context and search_task_id is not None: progress_context.stop()
        
    return found_items, None


# === Organization Plan Generation (Heuristic) ===
def generate_heuristic_organization_plan(base_path: str, strategy: str = "by_type") -> dict:
    """
    Generates a simple organization plan based on a heuristic (e.g., by file type).
    Returns: {"plan_steps": list_of_actions, "explanation": str}
    Actions: {"action": "create_folder", "path": "relative_subfolder_path_from_base"}
             {"action": "move", "source": "relative_file_path_from_base", "destination": "relative_new_file_path_from_base"}
    """
    plan = {"plan_steps": [], "explanation": f"Heuristic plan to organize files in '{base_path}' by {strategy}."}
    if not os.path.isdir(base_path):
        plan["explanation"] = f"Error: Base path '{base_path}' is not a directory."
        return plan

    items, error = list_folder_contents_simple(base_path)
    if error:
        plan["explanation"] = f"Error listing contents for plan: {error}"
        return plan

    if not items:
        plan["explanation"] = "No items to organize in the folder."
        return plan

    created_folders_in_plan = set() # Track folders we plan to create to avoid duplicates

    if strategy == "by_type":
        type_map = {} # e.g., ".txt" -> "Text_Files"
        for item in items:
            if item["type"] == "file":
                name, ext = os.path.splitext(item["name"])
                ext_lower = ext.lower()
                if not ext_lower: continue # Skip files without extension

                # Simplified folder naming by extension category
                target_subfolder_name = None
                if ext_lower in SEARCH_TYPE_KEYWORDS.get("image", []) + SEARCH_TYPE_KEYWORDS.get("picture", []) + SEARCH_TYPE_KEYWORDS.get("photo", []):
                    target_subfolder_name = "Images"
                elif ext_lower in SEARCH_TYPE_KEYWORDS.get("document", []) + [".pdf", ".doc", ".docx", ".txt"]: # Broaden document types
                    target_subfolder_name = "Documents"
                elif ext_lower in SEARCH_TYPE_KEYWORDS.get("video", []):
                    target_subfolder_name = "Videos"
                elif ext_lower in SEARCH_TYPE_KEYWORDS.get("audio", []):
                    target_subfolder_name = "Audio"
                elif ext_lower in SEARCH_TYPE_KEYWORDS.get("archive", []):
                    target_subfolder_name = "Archives"
                elif ext_lower in SEARCH_TYPE_KEYWORDS.get("code file", []) + [".py", ".js", ".html", ".css"]:
                    target_subfolder_name = "Code_Scripts"
                else:
                    target_subfolder_name = f"{ext_lower[1:].upper()}_Files" # e.g., JPG_Files (remove leading dot)
                
                if target_subfolder_name not in created_folders_in_plan:
                    plan["plan_steps"].append({"action_type": "CREATE_FOLDER", "path": os.path.join(base_path, target_subfolder_name)}) # Use absolute paths for plan
                    created_folders_in_plan.add(target_subfolder_name) # Store relative name for tracking
                
                # Ensure destination doesn't try to move into itself if base_path is already a category folder
                # And ensure source/destination are different
                destination_path = os.path.join(base_path, target_subfolder_name, item["name"])
                source_path = os.path.join(base_path, item["name"])
                if os.path.normpath(os.path.join(base_path, target_subfolder_name)) != os.path.normpath(base_path) and \
                   os.path.normpath(source_path) != os.path.normpath(destination_path) :
                    plan["plan_steps"].append({
                        "action_type": "MOVE_ITEM", # Match LLM plan action_type
                        "source": source_path, 
                        "destination": destination_path
                    })
    
    elif strategy == "by_first_letter":
        for item in items:
            if item["type"] == "file" or item["type"] == "directory": # Can organize folders too
                first_char = item["name"][0].upper() if item["name"] else "_"
                target_subfolder_name_rel = "" # Relative name for tracking and folder creation
                if 'A' <= first_char <= 'Z':
                    target_subfolder_name_rel = f"{first_char}_Files"
                elif '0' <= first_char <= '9':
                    target_subfolder_name_rel = "0-9_Files"
                else:
                    target_subfolder_name_rel = "Symbols_Files"

                if target_subfolder_name_rel not in created_folders_in_plan:
                    plan["plan_steps"].append({"action_type": "CREATE_FOLDER", "path": os.path.join(base_path, target_subfolder_name_rel)})
                    created_folders_in_plan.add(target_subfolder_name_rel)
                
                destination_path = os.path.join(base_path, target_subfolder_name_rel, item["name"])
                source_path = os.path.join(base_path, item["name"])

                if os.path.normpath(os.path.join(base_path, target_subfolder_name_rel)) != os.path.normpath(base_path) and \
                   item["name"] != target_subfolder_name_rel and \
                   os.path.normpath(source_path) != os.path.normpath(destination_path): 
                    plan["plan_steps"].append({
                        "action_type": "MOVE_ITEM",
                        "source": source_path,
                        "destination": destination_path
                    })
    else:
        plan["explanation"] = f"Unsupported heuristic strategy: {strategy}."
        plan["plan_steps"] = []

    return plan

# Placeholder if you want to test fs_utils.py directly
if __name__ == "__main__":
    print("Testing fs_utils.py functions...")
    # Example: Create a dummy structure
    test_base = "fs_utils_test_dir"
    if os.path.exists(test_base): shutil.rmtree(test_base)
    os.makedirs(os.path.join(test_base, "Images"), exist_ok=True) # Pre-existing folder
    os.makedirs(os.path.join(test_base, "Docs"), exist_ok=True)   # Pre-existing folder
    
    # Create some files directly in test_base
    with open(os.path.join(test_base, "annual_report.docx"), "w") as f: f.write("doc content for annual report")
    with open(os.path.join(test_base, "budget_plan.xlsx"), "w") as f: f.write("excel content for budget")
    with open(os.path.join(test_base, "holiday_pic.jpg"), "w") as f: f.write("jpg content for holiday")
    with open(os.path.join(test_base, "main_script.py"), "w") as f: f.write("# python script for main logic")
    with open(os.path.join(test_base, "backup.zip"), "w") as f: f.write("zip content for backup")
    with open(os.path.join(test_base, "notes.txt"), "w") as f: f.write("text notes about project alpha")
    with open(os.path.join(test_base, "unknown_file.xyz"), "w") as f: f.write("xyz content unknown")
    os.makedirs(os.path.join(test_base, "Alpha_Project_Folder"), exist_ok=True)
    with open(os.path.join(test_base, "Alpha_Project_Folder", "alpha_data.csv"), "w") as f: f.write("alpha specific csv")


    print("\n--- Testing list_folder_contents_simple ---")
    items, err = list_folder_contents_simple(test_base)
    if err: print(f"Error: {err}")
    else: 
        for item in items: print(f"  {item['name']} ({item['type']}) - {item['size_readable']}")

    print("\n--- Testing is_file_type_match ---")
    print(f"holiday_pic.jpg is 'image': {is_file_type_match(os.path.join(test_base, 'holiday_pic.jpg'), 'image')}")
    print(f"annual_report.docx is '.docx': {is_file_type_match(os.path.join(test_base, 'annual_report.docx'), '.docx')}")
    print(f"main_script.py is 'document': {is_file_type_match(os.path.join(test_base, 'main_script.py'), 'document')}")
    print(f"main_script.py is 'code file': {is_file_type_match(os.path.join(test_base, 'main_script.py'), 'code file')}")

    print("\n--- Testing generate_heuristic_organization_plan by_type ---")
    plan_type = generate_heuristic_organization_plan(test_base, "by_type")
    print(f"Explanation: {plan_type['explanation']}")
    for step in plan_type["plan_steps"]: print(f"  {step}")

    print("\n--- Testing generate_heuristic_organization_plan by_first_letter ---")
    plan_alpha_h = generate_heuristic_organization_plan(test_base, "by_first_letter")
    print(f"Explanation: {plan_alpha_h['explanation']}")
    for step in plan_alpha_h["plan_steps"]: print(f"  {step}")
    
    print("\n--- Testing search_files_recursive (no LLM connector) ---")
    print("Searching for '.py' files:")
    found_py, err_py = search_files_recursive(test_base, ".py", None)
    if err_py: print(f"  Search Error: {err_py}")
    else:
        for item in found_py: print(f"  Found: {item['path']}")

    print("Searching for 'image' files:")
    found_img, err_img = search_files_recursive(test_base, "image", None)
    if err_img: print(f"  Search Error: {err_img}")
    else:
        for item in found_img: print(f"  Found: {item['path']}")

    print("Searching for files 'containing \"project alpha\"':")
    # Note: This will only find in .txt, .py etc. by default get_file_content_for_search
    found_content, err_content = search_files_recursive(test_base, "files containing \"project alpha\"", None)
    if err_content: print(f"  Search Error: {err_content}")
    else:
        for item in found_content: print(f"  Found: {item['path']}")

    print("Searching for 'Alpha_Project_Folder' (as name search):")
    # This search_files_recursive primarily finds *files*. To find folders, a different approach or modified function would be needed.
    # The current implementation of os.walk targets files in the `for filename in files:` loop.
    # For a simple name search that could be a file OR folder, the logic would need adjustment.
    # Let's test searching for a file within that folder.
    found_alpha_content, err_alpha_content = search_files_recursive(test_base, "alpha_data.csv", None)
    if err_alpha_content: print(f"  Search Error: {err_alpha_content}")
    else:
        for item in found_alpha_content: print(f"  Found: {item['path']}")


    # Cleanup (optional, comment out if you want to inspect the directory)
    # if os.path.exists(test_base): shutil.rmtree(test_base)
    print("\nDone testing fs_utils.py.")