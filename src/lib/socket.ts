import { Server as IOServer } from 'socket.io';
import type { Server as HTTPServer } from 'http';

let io: IOServer | null = null;

export function initSocket(server: HTTPServer) {
  if (!io) {
    io = new IOServer(server, {
      path: '/api/socket',
    });
    io.on('connection', (socket) => {
      console.log('socket connected', socket.id);
    });
  }
  return io;
}

export function getIO(): IOServer {
  if (!io) {
    throw new Error('Socket.io not initialized');
  }
  return io;
}
