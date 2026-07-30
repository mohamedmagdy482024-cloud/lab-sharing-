# GitHub Push Guide

This guide explains how your local folder was pushed to GitHub and completely replaced the old contents, and how you can push regular updates in the future.

## How the initial overwrite was done

To completely overwrite the GitHub `main` branch with your local files, the following commands were run in your terminal:

```bash
# 1. Initialize a brand new git repository in your local folder
git init

# 2. Add all local files to the new repository
git add .

# 3. Save (commit) these files
git commit -m "Initial commit of local folder"

# 4. Link your local repository to your remote GitHub repository
git remote add origin https://github.com/mohamedmagdy482024-cloud/lab-sharing-.git

# 5. Make sure the local branch is named 'main'
git branch -M main

# 6. Force push to GitHub. 
# The --force flag tells GitHub to permanently delete whatever was there 
# and replace it with this upload.
git push -u origin main --force
```

## How to push updates in the future

Now that your repository is set up, you **should not** use the `--force` flag again. When you make changes to your code in the future and want to upload them to GitHub, run these standard commands:

```bash
# 1. Add your modified files
git add .

# 2. Commit your changes with a descriptive message
git commit -m "Fixed a bug in the UI layout"

# 3. Push the changes normally
git push origin main
```

## Troubleshooting: "Authentication failed" Error

If you see this error when running `git push`:
`fatal: Authentication failed for 'https://github.com/...'`

It means GitHub is rejecting your password. **GitHub no longer accepts account passwords for terminal pushes.** Instead, you must use a **Personal Access Token (PAT)**.

### How to push using a Token:

1. **Generate a Token on GitHub:**
   - Go to GitHub.com → **Settings** → **Developer Settings** (at the very bottom of the left sidebar) → **Personal access tokens** → **Tokens (classic)**.
   - Click **Generate new token (classic)**.
   - Give it a note (e.g., "Ubuntu Terminal"), set expiration, and **check the `repo` box** to give it push access.
   - Click Generate and **copy the token** (it starts with `ghp_`).

2. **Push your code using the Token:**
   When you run `git push origin main`, it will ask for your Username and Password.
   - **Username:** `mohamedmagdy482024-cloud`
   - **Password:** Paste the Token you just copied (you won't see it as you type, just paste and press Enter).

### (Optional) Save your Token so it doesn't ask every time
To make Git remember your credentials so you don't have to copy-paste the token every time, run this command once:
```bash
git config --global credential.helper store
```
The next time you push and enter your token, it will be saved permanently on this computer.
