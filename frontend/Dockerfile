# Build stage
FROM node:22-alpine AS builder

WORKDIR /app

ARG BUILD_VERSION=unknown

# pnpm via corepack — version comes from the "packageManager" field in package.json
RUN corepack enable

# Copy package files
COPY package.json pnpm-lock.yaml ./

# Install dependencies
RUN pnpm install --frozen-lockfile

# Copy source files
COPY . .

# Write version file for generateBuildId in next.config.ts
RUN echo "$BUILD_VERSION" > /app/VERSION

# Build the application
RUN pnpm build

# Production stage
FROM node:22-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production

# Install curl for health checks
RUN apk add --no-cache curl

# Create non-root user
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Copy built application
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
# Resolves the client address before Next.js sees the request (see the file)
COPY --from=builder /app/server-wrapper.cjs ./server-wrapper.cjs

# Set ownership
RUN chown -R nextjs:nodejs /app

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server-wrapper.cjs"]
