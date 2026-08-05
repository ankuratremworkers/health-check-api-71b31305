FROM node:22-alpine AS build

WORKDIR /app

# Install dependencies first (layer caching)
COPY package*.json ./

RUN npm install --include=dev --legacy-peer-deps

COPY . .

ENV VITE_BASE_PATH=/health_check_api_71b313_frontend/

RUN npx vite build

FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html

COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD wget -q --spider http://127.0.0.1:8000/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
