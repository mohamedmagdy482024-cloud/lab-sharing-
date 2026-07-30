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
