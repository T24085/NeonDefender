import React from 'react';

export type Cell = {
  value: number | null;
  readonly?: boolean;
};

export interface GameBoardProps {
  board: Cell[][];
  onInput?: (r: number, c: number, value: number | null) => void;
}

export const GameBoard: React.FC<GameBoardProps> = ({ board, onInput }) => {
  const handleChange = (r: number, c: number, e: React.ChangeEvent<HTMLInputElement>) => {
    const v = parseInt(e.target.value, 10);
    onInput?.(r, c, isNaN(v) ? null : v);
  };

  return (
    <div className="grid grid-cols-9 gap-1">
      {board.map((row, r) =>
        row.map((cell, c) => (
          <input
            key={`${r}-${c}`}
            className="w-8 h-8 text-center border"
            value={cell.value ?? ''}
            onChange={(e) => handleChange(r, c, e)}
            readOnly={cell.readonly}
          />
        )),
      )}
    </div>
  );
};

export default GameBoard;
