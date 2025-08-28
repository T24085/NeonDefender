import crypto from 'crypto';

export type Board = (number | null)[][];
export type Difficulty = 'EASY' | 'MEDIUM' | 'HARD' | 'EXPERT';

function mulberry32(a: number) {
  return function () {
    let t = (a += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function clone(board: Board): Board {
  return board.map((row) => row.slice());
}

function isValid(board: Board, r: number, c: number, val: number): boolean {
  for (let i = 0; i < 9; i++) {
    if (board[r][i] === val || board[i][c] === val) return false;
  }
  const br = Math.floor(r / 3) * 3;
  const bc = Math.floor(c / 3) * 3;
  for (let i = 0; i < 3; i++) {
    for (let j = 0; j < 3; j++) {
      if (board[br + i][bc + j] === val) return false;
    }
  }
  return true;
}

function solveBoard(board: Board): boolean {
  for (let r = 0; r < 9; r++) {
    for (let c = 0; c < 9; c++) {
      if (board[r][c] === null) {
        for (let v = 1; v <= 9; v++) {
          if (isValid(board, r, c, v)) {
            board[r][c] = v;
            if (solveBoard(board)) return true;
            board[r][c] = null;
          }
        }
        return false;
      }
    }
  }
  return true;
}

function countSolutions(board: Board, limit = 2): number {
  let count = 0;
  const cloneBoard = clone(board);
  function backtrack(): boolean {
    for (let r = 0; r < 9; r++) {
      for (let c = 0; c < 9; c++) {
        if (cloneBoard[r][c] === null) {
          for (let v = 1; v <= 9; v++) {
            if (isValid(cloneBoard, r, c, v)) {
              cloneBoard[r][c] = v;
              if (backtrack()) return true;
              cloneBoard[r][c] = null;
            }
          }
          return false;
        }
      }
    }
    count++;
    return count >= limit;
  }
  backtrack();
  return count;
}

function generateSolved(rng: () => number): Board {
  const board: Board = Array.from({ length: 9 }, () => Array(9).fill(null));
  function fill(r = 0, c = 0): boolean {
    if (r === 9) return true;
    const nr = c === 8 ? r + 1 : r;
    const nc = c === 8 ? 0 : c + 1;
    const nums = [1, 2, 3, 4, 5, 6, 7, 8, 9].sort(() => rng() - 0.5);
    for (const n of nums) {
      if (isValid(board, r, c, n)) {
        board[r][c] = n;
        if (fill(nr, nc)) return true;
        board[r][c] = null;
      }
    }
    return false;
  }
  fill();
  return board;
}

export function generatePuzzle(difficulty: Difficulty, seed = Date.now().toString()) {
  const rng = mulberry32(hashCode(seed));
  const solution = generateSolved(rng);
  const puzzle = clone(solution);
  const targetGivens = { EASY: 40, MEDIUM: 32, HARD: 26, EXPERT: 22 }[difficulty];
  const cells = Array.from({ length: 81 }, (_, i) => i).sort(() => rng() - 0.5);
  let removed = 0;
  for (const idx of cells) {
    if (81 - removed <= targetGivens) break;
    const r = Math.floor(idx / 9);
    const c = idx % 9;
    const backup = puzzle[r][c];
    puzzle[r][c] = null;
    const copies = clone(puzzle);
    if (countSolutions(copies) !== 1) {
      puzzle[r][c] = backup;
    } else {
      removed++;
    }
  }
  const hash = crypto
    .createHash('sha256')
    .update(solution.flat().join(''))
    .digest('hex');
  return { seed, puzzle, solution, solutionHash: hash };
}

function hashCode(str: string): number {
  let h = 0;
  for (let i = 0; i < str.length; i++) {
    h = Math.imul(31, h) + str.charCodeAt(i) | 0;
  }
  return h;
}

export function solve(puzzle: Board): Board {
  const board = clone(puzzle);
  if (!solveBoard(board)) throw new Error('Unsolvable puzzle');
  return board;
}
