FROM mcr.microsoft.com/playwright:v1.49.0-jammy
WORKDIR /app
COPY package.json .
RUN npm install --no-audit --no-fund
COPY sync.js .
CMD ["node", "sync.js"]
