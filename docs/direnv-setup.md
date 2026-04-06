---
layout: default
title: Python Setup
nav_order: 2
---

# Direnv setup

## Environment Management with `direnv`

The `development` directory contains a script to configure `direnv` for automated environment management. This is optional but recommended for a smoother development workflow.

1.  **Run the setup script:**
    ```bash
    cd development
    ./setup-direnv.sh
    ```

2.  **Allow direnv:**
    After configuration, `direnv` will ask for permission. Run `direnv allow` in the project root.

    Now, `direnv` will automatically load the environment variables and activate the virtual environment when entering the project directory.

## Secure Secret Storage with GPG

For enhanced security, environment files can be encrypted using GPG. The included `.envrc` script supports automatic decryption of files named `.secrets.*`.

1.  **Import GPG Key:**
    ```shell
    gpg --import ~/.ssh/id_rsa
    gpg --list-secret-keys
    ```

2.  **Encrypt Environment File:**
    The following command encrypts `.env.development`.
    ```shell
    mkdir -p secrets
    gpg -r <your-key-id> -o secrets/development.gpg -e .env.development
    ```
    Ensure the unencrypted source file (`.env.development`) is included in `.gitignore`.

## Tips
- Use `direnv` to avoid manual activation of virtual environments and loading of secrets.
- For more on configuration, see [Configuration](configuration.md).
- For local development, see [Local Development](local-dev.md).
