```bash
source env/bin/activate
which pip
pip install pip-tools
pip-sync requirements.txt
make week
make pdf week=42
sudo apt install pandoc
make pdf week=42
sudo apt install texlive-xetex
```

```bash
docker build -t menu-app .
docker run -p 80:5000 menu-app
```

# Docker GitHub Container Registry (GHCR) Guide

## Creating a Personal Access Token (PAT)
1. Go to GitHub Settings → Developer Settings → Personal Access Tokens
2. Choose "Tokens (classic)" or "Fine-grained tokens"
3. Generate new token with required permissions:
   - `write:packages`
   - `read:packages`
   - `delete:packages` (optional)
4. Save the token securely (e.g., in 1Password)
5. Note the token name shown in GitHub settings (this will be your username for docker login)

## Pushing Images to GHCR

1. Login to GitHub Container Registry:
```bash
# Replace TOKEN_NAME with the name of your token from GitHub settings
# Replace YOUR_PAT with your actual PAT
echo YOUR_PAT | docker login ghcr.io -u TOKEN_NAME --password-stdin
```

2. Tag your local image:
```bash
docker tag menu-app:latest ghcr.io/julietkiloromeo/menu-app:latest
```

3. Push the image:
```bash
docker push ghcr.io/julietkiloromeo/menu-app:latest
```

## Pulling Images on a New Machine

1. Login to GHCR:
```bash
# Replace TOKEN_NAME and YOUR_PAT as before
echo YOUR_PAT | docker login ghcr.io -u TOKEN_NAME --password-stdin
```

2. Pull the image:
```bash
docker pull ghcr.io/julietkiloromeo/menu-app:latest
```

## Troubleshooting

- If login fails, verify:
  - Token name is correct (from GitHub settings, not your GitHub username)
  - PAT hasn't expired
  - PAT has correct permissions
- If push fails, ensure:
  - Repository exists and is properly configured for packages
  - You have appropriate permissions on the repository
  - Image is tagged correctly with the ghcr.io prefix

## Security Notes

- Never commit your PAT to version control
- Use environment variables or secure secret management (like 1Password) to store PATs
- Consider using fine-grained tokens with minimal necessary permissions
- Regularly rotate your PATs