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

#!/usr/bin/env bash

info() {
    echo -e "\033[0;32m[INFO]\033[0m $1"
}

error() {
    echo -e "\033[0;31m[ERROR]\033[0m $1"
}

warn() {
    echo -e "\033[0;33m[WARN]\033[0m $1"
}

BLUE="\033[34m"
RESET="\033[0m"

# Get Python version
PYTHON_VERSION=$(python3 --version 2>&1)

# Create venv if missing
if [ ! -d .venv ]; then
    info "Creating Python ${BLUE}$PYTHON_VERSION${RESET} venv ..."
    if ! python3 -m venv .venv; then
        error "Failed to create virtual environment."
        error "You might need to install ${BLUE}python3-venv${RESET} or ${BLUE}python3-full${RESET}."
        error "On Debian/Ubuntu: sudo apt install python3-venv"
        rm -rf .venv
        return 1
    fi
fi

# Activate venv
if [ -f .venv/bin/activate ]; then
    info "Activating Python ${BLUE}$PYTHON_VERSION${RESET} virtual environment ..."
    source .venv/bin/activate
else
    error "Virtual environment not found or invalid. Removing ${BLUE}.venv${RESET} ..."
    rm -rf .venv
    error "Try again now"
    return 1
fi

# Install requirements if file exists
if [ -f requirements.txt ]; then
    info "Installing dependencies from ${BLUE}requirements.txt${RESET} ..."
    if ! pip install -q -r requirements.txt; then
        error "Failed to install dependencies."
        return 1
    fi
fi

# Decrypt secrets from secrets/*.gpg to .secrets.*
if [ -d secrets ]; then
    for gpg_file in secrets/*.gpg; do
        if [ -f "$gpg_file" ]; then
            env_name=$(basename "$gpg_file" .gpg)
            env_file=".secrets.$env_name"

            # Decrypt if .env file doesn't exist or is older than the encrypted file
            if [ ! -f "$env_file" ] || [ "$gpg_file" -nt "$env_file" ]; then
                info "Decrypting ${BLUE}$gpg_file${RESET} to ${BLUE}$env_file${RESET} ..."
                if ! gpg --quiet --batch --yes --decrypt --output "$env_file" "$gpg_file"; then
                    warn "Failed to decrypt ${BLUE}$gpg_file${RESET}"
                fi
            fi
        fi
    done
fi

# Detect and load .secrets.* files
for env_file in .secrets.*; do
    if [ -f "$env_file" ]; then
        info "Loading environment variables from ${BLUE}$env_file${RESET} ..."
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