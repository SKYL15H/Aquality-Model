import json
import os

def main():
    ipynb_path = r"d:\Lombuy IPBuy\Model\Model_Earth.ipynb"
    py_path = r"d:\Lombuy IPBuy\Model\Model_Coast-Vision.py"
    
    if not os.path.exists(ipynb_path):
        print(f"Error: {ipynb_path} not found!")
        return
        
    print(f"Reading {ipynb_path}...")
    with open(ipynb_path, "r", encoding="utf-8") as f:
        nb = json.load(f)
        
    py_lines = []
    for cell in nb["cells"]:
        cell_type = cell["cell_type"]
        source = cell["source"]
        
        if cell_type == "markdown":
            py_lines.append("# %% [markdown]\n")
            for line in source:
                # Handle newlines gracefully
                clean_line = line.rstrip("\n")
                if clean_line:
                    py_lines.append(f"# {clean_line}\n")
                else:
                    py_lines.append("#\n")
            py_lines.append("\n")
            
        elif cell_type == "code":
            py_lines.append("# %%\n")
            for line in source:
                py_lines.append(line)
            # Ensure proper spacing at the end of the cell
            if py_lines and not py_lines[-1].endswith("\n"):
                py_lines[-1] += "\n"
            py_lines.append("\n")
            
    print(f"Writing {py_path}...")
    with open(py_path, "w", encoding="utf-8") as f:
        f.writelines(py_lines)
    print("Conversion completed successfully!")

if __name__ == "__main__":
    main()
