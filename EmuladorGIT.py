import tkinter as tk
from tkinter import scrolledtext, filedialog
import os
import json
import shutil
import hashlib
from datetime import datetime
import urllib.request
import zipfile

class GitEmulator:
    def __init__(self, cwd):
        self.cwd = cwd
        self.config = {}
        self.load_config()
    
    def load_config(self):
        """Carrega configuração global do Git"""
        config_path = os.path.join(os.path.expanduser("~"), ".gitemulator_config")
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                self.config = json.load(f)
        else:
            self.config = {
                "user.name": "User",
                "user.email": "user@example.com"
            }
    
    def save_config(self):
        """Salva configuração global"""
        config_path = os.path.join(os.path.expanduser("~"), ".gitemulator_config")
        with open(config_path, 'w') as f:
            json.dump(self.config, f)
    
    def init(self):
        """Inicializa repositório Git"""
        git_dir = os.path.join(self.cwd, ".git")
        if os.path.exists(git_dir):
            return "Repositório Git já inicializado."
        
        os.makedirs(os.path.join(git_dir, "objects"), exist_ok=True)
        os.makedirs(os.path.join(git_dir, "refs", "heads"), exist_ok=True)
        os.makedirs(os.path.join(git_dir, "refs", "tags"), exist_ok=True)
        
        # Cria estrutura inicial
        with open(os.path.join(git_dir, "HEAD"), 'w') as f:
            f.write("ref: refs/heads/main\n")
        
        with open(os.path.join(git_dir, "config"), 'w') as f:
            f.write("[core]\n\trepositoryformatversion = 0\n")
        
        # Inicializa index vazio
        index_file = os.path.join(git_dir, "index.json")
        with open(index_file, 'w') as f:
            json.dump({"staged": {}, "commits": [], "branches": {"main": None}, "current_branch": "main"}, f)
        
        return f"Repositório Git inicializado em {self.cwd}"
    
    def get_git_dir(self):
        """Encontra o diretório .git"""
        current = self.cwd
        while current != os.path.dirname(current):
            git_dir = os.path.join(current, ".git")
            if os.path.exists(git_dir):
                return git_dir
            current = os.path.dirname(current)
        return None
    
    def load_index(self):
        """Carrega o index do repositório"""
        git_dir = self.get_git_dir()
        if not git_dir:
            raise Exception("fatal: not a git repository")
        
        index_file = os.path.join(git_dir, "index.json")
        with open(index_file, 'r') as f:
            return json.load(f)
    
    def save_index(self, index):
        """Salva o index"""
        git_dir = self.get_git_dir()
        index_file = os.path.join(git_dir, "index.json")
        with open(index_file, 'w') as f:
            json.dump(index, f, indent=2)
    
    def status(self):
        """Mostra status do repositório"""
        try:
            index = self.load_index()
            output = []
            
            output.append(f"On branch {index['current_branch']}")
            
            if not index['commits']:
                output.append("\nNo commits yet\n")
            
            # Arquivos staged
            if index['staged']:
                output.append("\nChanges to be committed:")
                output.append("  (use \"git reset HEAD <file>...\" to unstage)\n")
                for file in index['staged']:
                    output.append(f"        modified:   {file}")
            
            # Arquivos não rastreados
            untracked = self.get_untracked_files(index)
            if untracked:
                output.append("\nUntracked files:")
                output.append("  (use \"git add <file>...\" to include in what will be committed)\n")
                for file in untracked:
                    output.append(f"        {file}")
            
            if not index['staged'] and not untracked:
                output.append("\nnothing to commit, working tree clean")
            
            return "\n".join(output)
        except Exception as e:
            return str(e)
    
    def get_untracked_files(self, index):
        """Lista arquivos não rastreados"""
        git_dir = self.get_git_dir()
        repo_root = os.path.dirname(git_dir)
        untracked = []
        
        for root, dirs, files in os.walk(repo_root):
            # Ignora .git
            if '.git' in root:
                continue
            
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, repo_root)
                
                # Verifica se não está no staged
                if rel_path not in index['staged']:
                    # Verifica se já foi commitado
                    committed = False
                    if index['commits']:
                        last_commit = index['commits'][-1]
                        if rel_path in last_commit.get('files', {}):
                            committed = True
                    
                    if not committed:
                        untracked.append(rel_path)
        
        return untracked
    
    def add(self, path):
        """Adiciona arquivo ao stage"""
        try:
            index = self.load_index()
            git_dir = self.get_git_dir()
            repo_root = os.path.dirname(git_dir)
            
            if path == ".":
                # Adiciona todos os arquivos
                untracked = self.get_untracked_files(index)
                for file in untracked:
                    file_path = os.path.join(repo_root, file)
                    if os.path.exists(file_path):
                        with open(file_path, 'rb') as f:
                            content = f.read()
                        index['staged'][file] = hashlib.sha256(content).hexdigest()
                
                self.save_index(index)
                return f"Added {len(untracked)} files"
            else:
                # Adiciona arquivo específico
                full_path = os.path.join(repo_root, path)
                if not os.path.exists(full_path):
                    return f"fatal: pathspec '{path}' did not match any files"
                
                with open(full_path, 'rb') as f:
                    content = f.read()
                
                index['staged'][path] = hashlib.sha256(content).hexdigest()
                self.save_index(index)
                return f"Added '{path}' to stage"
        except Exception as e:
            return str(e)
    
    def commit(self, message):
        """Cria um commit"""
        try:
            index = self.load_index()
            
            if not index['staged']:
                return "nothing to commit, working tree clean"
            
            commit = {
                "hash": hashlib.sha256(f"{message}{datetime.now()}".encode()).hexdigest()[:8],
                "message": message,
                "author": f"{self.config.get('user.name', 'User')} <{self.config.get('user.email', 'user@example.com')}>",
                "date": datetime.now().isoformat(),
                "files": dict(index['staged']),
                "branch": index['current_branch']
            }
            
            index['commits'].append(commit)
            index['branches'][index['current_branch']] = commit['hash']
            index['staged'] = {}
            
            self.save_index(index)
            return f"[{index['current_branch']} {commit['hash']}] {message}\n {len(commit['files'])} files changed"
        except Exception as e:
            return str(e)
    
    def log(self):
        """Mostra histórico de commits"""
        try:
            index = self.load_index()
            
            if not index['commits']:
                return "No commits yet"
            
            output = []
            for commit in reversed(index['commits']):
                output.append(f"commit {commit['hash']}")
                output.append(f"Author: {commit['author']}")
                output.append(f"Date:   {commit['date']}\n")
                output.append(f"    {commit['message']}\n")
            
            return "\n".join(output)
        except Exception as e:
            return str(e)
    
    def branch(self, name=None, args=""):
        """Gerencia branches"""
        try:
            index = self.load_index()
            
            if name is None:
                # Lista branches
                output = []
                for branch in index['branches']:
                    prefix = "* " if branch == index['current_branch'] else "  "
                    output.append(f"{prefix}{branch}")
                return "\n".join(output)
            else:
                # Cria nova branch
                if name in index['branches']:
                    return f"fatal: A branch named '{name}' already exists."
                
                current_commit = index['branches'][index['current_branch']]
                index['branches'][name] = current_commit
                self.save_index(index)
                return f"Branch '{name}' created"
        except Exception as e:
            return str(e)
    
    def checkout(self, branch):
        """Muda de branch"""
        try:
            index = self.load_index()
            
            if branch not in index['branches']:
                return f"error: pathspec '{branch}' did not match any file(s) known to git"
            
            if index['staged']:
                return "error: Your local changes would be overwritten by checkout.\nPlease commit your changes first."
            
            index['current_branch'] = branch
            self.save_index(index)
            return f"Switched to branch '{branch}'"
        except Exception as e:
            return str(e)
    
    def clone(self, url):
        """Clone um repositório (simulado - apenas baixa ZIP do GitHub)"""
        try:
            # Extrai nome do repositório
            repo_name = url.rstrip('/').split('/')[-1].replace('.git', '')
            target_dir = os.path.join(self.cwd, repo_name)
            
            if os.path.exists(target_dir):
                return f"fatal: destination path '{repo_name}' already exists"
            
            # Tenta baixar como ZIP do GitHub
            if 'github.com' in url:
                zip_url = url.replace('.git', '') + '/archive/refs/heads/main.zip'
                output = f"Cloning into '{repo_name}'...\n"
                output += f"Downloading from {zip_url}\n"
                
                try:
                    zip_path = os.path.join(self.cwd, f"{repo_name}.zip")
                    urllib.request.urlretrieve(zip_url, zip_path)
                    
                    # Extrai ZIP
                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        zip_ref.extractall(self.cwd)
                    
                    # Renomeia pasta extraída
                    extracted = os.path.join(self.cwd, f"{repo_name}-main")
                    if os.path.exists(extracted):
                        os.rename(extracted, target_dir)
                    
                    os.remove(zip_path)
                    
                    output += f"Successfully cloned repository to {target_dir}"
                    return output
                except:
                    return f"fatal: unable to download repository. Try: main, master, or check URL"
            
            return "Clone functionality requires GitHub URL (e.g., https://github.com/user/repo)"
        except Exception as e:
            return f"fatal: {str(e)}"
    
    def config(self, key=None, value=None):
        """Configura Git"""
        if key is None:
            output = []
            for k, v in self.config.items():
                output.append(f"{k}={v}")
            return "\n".join(output) if output else "No configuration set"
        
        if value is None:
            return self.config.get(key, f"No value found for '{key}'")
        
        self.config[key] = value
        self.save_config()
        return f"Configuration '{key}' set to '{value}'"

class GitTerminal:
    def __init__(self, root):
        self.root = root
        self.root.title("Emulated/Git/$$")
        self.root.geometry("900x600")
        self.root.configure(bg="#1e1e1e")
        
        self.cwd = os.getcwd()
        self.git = GitEmulator(self.cwd)
        
        # Frame principal
        main_frame = tk.Frame(root, bg="#1e1e1e")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Área de output
        self.output_area = scrolledtext.ScrolledText(
            main_frame,
            wrap=tk.WORD,
            bg="#0c0c0c",
            fg="#00ff00",
            insertbackground="#00ff00",
            font=("Consolas", 10),
            state=tk.DISABLED
        )
        self.output_area.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Frame para input
        input_frame = tk.Frame(main_frame, bg="#1e1e1e")
        input_frame.pack(fill=tk.X)
        
        # Label do prompt
        self.prompt_label = tk.Label(
            input_frame,
            text=f"git@{os.path.basename(self.cwd)}$",
            bg="#1e1e1e",
            fg="#00ff00",
            font=("Consolas", 10, "bold")
        )
        self.prompt_label.pack(side=tk.LEFT, padx=(0, 5))
        
        # Campo de entrada
        self.input_field = tk.Entry(
            input_frame,
            bg="#0c0c0c",
            fg="#00ff00",
            insertbackground="#00ff00",
            font=("Consolas", 10),
            relief=tk.FLAT
        )
        self.input_field.pack(fill=tk.X, expand=True)
        self.input_field.bind("<Return>", self.execute_command)
        self.input_field.bind("<Up>", self.history_up)
        self.input_field.bind("<Down>", self.history_down)
        self.input_field.focus()
        
        self.command_history = []
        self.history_index = 0
        
        # Mensagem de boas-vindas
        self.write_output("=" * 60)
        self.write_output("  EMULATED/GIT/$$ - Terminal Git Emulador v2.0")
        self.write_output("  Git Emulado Internamente - Não requer Git instalado!")
        self.write_output("=" * 60)
        self.write_output(f"Diretório atual: {self.cwd}")
        self.write_output("Digite 'help' para ver comandos disponíveis\n")
    
    def write_output(self, text, color="#00ff00"):
        self.output_area.config(state=tk.NORMAL)
        self.output_area.insert(tk.END, text + "\n")
        self.output_area.see(tk.END)
        self.output_area.config(state=tk.DISABLED)
    
    def update_prompt(self):
        self.prompt_label.config(text=f"git@{os.path.basename(self.cwd)}$")
    
    def history_up(self, event):
        if self.command_history and self.history_index > 0:
            self.history_index -= 1
            self.input_field.delete(0, tk.END)
            self.input_field.insert(0, self.command_history[self.history_index])
    
    def history_down(self, event):
        if self.command_history and self.history_index < len(self.command_history) - 1:
            self.history_index += 1
            self.input_field.delete(0, tk.END)
            self.input_field.insert(0, self.command_history[self.history_index])
        elif self.history_index == len(self.command_history) - 1:
            self.history_index = len(self.command_history)
            self.input_field.delete(0, tk.END)
    
    def execute_command(self, event):
        command = self.input_field.get().strip()
        
        if not command:
            return
        
        self.command_history.append(command)
        self.history_index = len(self.command_history)
        
        self.write_output(f"git@{os.path.basename(self.cwd)}$ {command}", "#ffff00")
        self.input_field.delete(0, tk.END)
        
        # Comandos internos
        if command == "clear":
            self.output_area.config(state=tk.NORMAL)
            self.output_area.delete(1.0, tk.END)
            self.output_area.config(state=tk.DISABLED)
            return
        
        if command in ["exit", "quit"]:
            self.root.quit()
            return
        
        if command == "help":
            self.show_help()
            return
        
        if command.startswith("cd "):
            self.change_directory(command[3:].strip())
            return
        
        if command == "pwd":
            self.write_output(self.cwd)
            return
        
        if command == "ls" or command == "dir":
            self.list_directory()
            return
        
        # Comandos Git
        self.process_git_command(command)
    
    def change_directory(self, path):
        try:
            if path == "..":
                new_path = os.path.dirname(self.cwd)
            elif os.path.isabs(path):
                new_path = path
            else:
                new_path = os.path.join(self.cwd, path)
            
            if os.path.exists(new_path) and os.path.isdir(new_path):
                self.cwd = os.path.abspath(new_path)
                self.git.cwd = self.cwd
                self.update_prompt()
            else:
                self.write_output(f"cd: {path}: No such file or directory", "#ff0000")
        except Exception as e:
            self.write_output(f"cd: {str(e)}", "#ff0000")
    
    def list_directory(self):
        try:
            items = os.listdir(self.cwd)
            for item in sorted(items):
                self.write_output(item)
        except Exception as e:
            self.write_output(f"Error: {str(e)}", "#ff0000")
    
    def process_git_command(self, command):
        parts = command.split()
        
        if not parts or parts[0] != "git":
            self.write_output(f"Command not found: {parts[0] if parts else ''}", "#ff0000")
            return
        
        if len(parts) < 2:
            self.write_output("usage: git <command> [<args>]", "#ff0000")
            return
        
        cmd = parts[1]
        args = parts[2:] if len(parts) > 2 else []
        
        try:
            if cmd == "init":
                result = self.git.init()
            elif cmd == "status":
                result = self.git.status()
            elif cmd == "add":
                if not args:
                    result = "Nothing specified, nothing added."
                else:
                    result = self.git.add(args[0])
            elif cmd == "commit":
                if "-m" in args:
                    idx = args.index("-m")
                    if idx + 1 < len(args):
                        message = " ".join(args[idx+1:])
                        result = self.git.commit(message)
                    else:
                        result = "error: option -m requires a value"
                else:
                    result = "error: commit message required (-m flag)"
            elif cmd == "log":
                result = self.git.log()
            elif cmd == "branch":
                if args:
                    result = self.git.branch(args[0])
                else:
                    result = self.git.branch()
            elif cmd == "checkout":
                if args:
                    result = self.git.checkout(args[0])
                else:
                    result = "error: branch name required"
            elif cmd == "clone":
                if args:
                    result = self.git.clone(args[0])
                else:
                    result = "fatal: You must specify a repository to clone."
            elif cmd == "config":
                if len(args) >= 2:
                    result = self.git.config(args[0], args[1])
                elif len(args) == 1:
                    result = self.git.config(args[0])
                else:
                    result = self.git.config()
            else:
                result = f"git: '{cmd}' is not a git command. See 'git help'."
            
            self.write_output(result)
        except Exception as e:
            self.write_output(f"Error: {str(e)}", "#ff0000")
    
    def show_help(self):
        help_text = """
╔═══════════════════════════════════════════════════════════╗
║           EMULATED/GIT/$$ - COMANDOS DISPONÍVEIS          ║
╚═══════════════════════════════════════════════════════════╝

COMANDOS INTERNOS:
  clear                    - Limpa o terminal
  help                     - Mostra esta ajuda
  exit / quit              - Fecha o terminal
  cd <diretório>           - Muda o diretório
  pwd                      - Mostra diretório atual
  ls / dir                 - Lista arquivos

COMANDOS GIT EMULADOS (funcionam sem Git instalado!):
  git init                 - Inicializa repositório
  git status               - Status do repositório
  git add <arquivo>        - Adiciona arquivo ao stage
  git add .                - Adiciona todos os arquivos
  git commit -m "msg"      - Cria commit
  git log                  - Histórico de commits
  git branch               - Lista branches
  git branch <nome>        - Cria branch
  git checkout <branch>    - Muda de branch
  git clone <url>          - Clona repositório do GitHub
  git config <key> <value> - Configura Git
  git config <key>         - Mostra configuração
  git config               - Lista todas configurações

NOTA: Este é um emulador Git completo! Não requer Git instalado.
      Clone funciona apenas com repositórios públicos do GitHub.

EXEMPLOS:
  git config user.name "Seu Nome"
  git config user.email "seu@email.com"
  git init
  git add .
  git commit -m "Initial commit"
  git clone https://github.com/usuario/repo
        """
        self.write_output(help_text)

def main():
    root = tk.Tk()
    app = GitTerminal(root)
    root.mainloop()

if __name__ == "__main__":
    main()