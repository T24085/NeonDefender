import { generatePuzzle, solve } from '../src/lib/sudoku';

test('generated puzzle solves correctly', () => {
  const { puzzle, solution } = generatePuzzle('EASY', 'demo');
  const solved = solve(puzzle);
  expect(solved).toEqual(solution);
});
