import os

def is_path_within_base(path_to_check: str, base_path: str) -> bool:
    try:
        abs_path_to_check = os.path.abspath(path_to_check)
        abs_base_path = os.path.abspath(base_path)
        # On case-insensitive filesystems, normalize case for comparison
        if os.name == 'nt': # Windows
            abs_path_to_check = abs_path_to_check.lower()
            abs_base_path = abs_base_path.lower()
            
        common_path = os.path.commonpath([abs_path_to_check, abs_base_path])
        # Ensure common_path is also case-normalized if on Windows for the final check
        if os.name == 'nt':
             common_path = common_path.lower()
             
        return common_path == abs_base_path
    except ValueError: # commonpath raises ValueError if paths are on different drives on Windows
        return False
    except Exception:
        return False