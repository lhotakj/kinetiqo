#!/usr/bin/env bash
set -e

( 
cd ..

# Logging functions
info() {
    printf "\033[0;32m[INFO]\033[0m %s\n"  "$1"
}

debug() {
    printf "\033[0;90m[DEBUG]\033[0m %s\n" "$1"
}

error() {
    printf "\033[0;31m[ERROR]\033[0m %s\n" "$1"
}

info " === This script will install and configure direnv for this project. ==="

# Ensure direnv is installed
if ! command -v direnv >/dev/null 2>&1; then
    info "Installing direnv..."
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        sudo apt update && sudo apt install -q -y direnv
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        brew install direnv
    else
        error "Unsupported OS. Install direnv manually."
        exit 1
    fi
fi

# Ensure shell integration
debug "Ensuring direnv shell integration..."
SHELL_RC=""
if [[ -n "$ZSH_VERSION" ]]; then
    SHELL_RC="$HOME/.zshrc"
elif [[ -n "$BASH_VERSION" ]]; then
    SHELL_RC="$HOME/.bashrc"
fi

if [[ -n "$SHELL_RC" ]]; then
    if ! grep -q 'eval "$(direnv hook' "$SHELL_RC"; then
        info "Adding direnv hook to $SHELL_RC."
        echo 'eval "$(direnv hook bash)"' >> "$SHELL_RC"
    fi
fi

info "Creating .envrc..."
# Create .envrc
cat > .envrc << 'EOF'

info() {
    printf "\033[0;32m[INFO]\033[0m %s\n" "$1"
}

# Get Python version
PYTHON_VERSION=$(python3 --version 2>&1)

# Create venv if missing
if [ ! -d .venv ]; then
    info "Creating Python $PYTHON_VERSION venv..."
    python3 -m venv .venv
fi

# Activate venv
info "Activating Python $PYTHON_VERSION venv..."
source .venv/bin/activate

# Install requirements if file exists
if [ -f requirements.txt ]; then
    info "Installing dependencies from requirements.txt ..."
    pip install -q -r requirements.txt
fi

# Detect and load .env.* files
for env_file in .env.*; do
    if [ -f "$env_file" ]; then
        info "Loading environment variables from $env_file..."
        set -a
        source "$env_file"
        set +a
    fi
done


EOF

# Allow direnv
direnv allow .

info "direnv setup complete. Please restart your shell to activate direnv."
)