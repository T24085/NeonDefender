# PuzzleRush Arena

A multiplayer Sudoku-like game built with Next.js, Prisma, NextAuth, and Socket.IO. This repository currently contains foundational code including:

- Prisma schema
- NextAuth configuration
- Socket.IO server wiring
- Sudoku puzzle generator and solver
- GameBoard React component
- Jest test for puzzle logic

## Development

```
cp .env.example .env
# Fill environment variables for DATABASE_URL, REDIS_URL, AUTH secrets
npm install
npx prisma migrate dev
npm run dev
```

## Testing

```
npm test
```

## License

MIT
