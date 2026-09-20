# GitHub Workflow

Repository: `https://github.com/VijeshVS/catalyst`

This workflow is triggered **only when the user asks to push code to GitHub**.

1. **Create a new branch** for the finalized changes using a descriptive feature/fix name. Never push directly to `main`.
2. **Fetch the latest `main`** and check the new branch for conflicts with `main`.
3. **Resolve all conflicts** before proceeding. Do not create the PR until the branch is conflict-free.
4. **Review and validate the changes**, then commit them to the new branch.
5. **Push the new branch** to GitHub.
6. **Create a Pull Request** from the new branch into `main`.
7. **Never push directly to `main`**, even if the user asks to push the code.

