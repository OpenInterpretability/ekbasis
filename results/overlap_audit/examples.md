# Overlap examples: a test question (ce_items) beside the training row it matched

Picked with random.Random(0), at most one per world family within each kind. Texts as stored; the training row's
questions are listed with their gold answers.

## A. same prompt, same question — seq, group T, item 6515
Match: training file `ftrain_mixG3` row 3748 (kind `floor`), identical prompt; state lines that differ: 0, action lines that differ: 0.

**Test item**

```
World: a line of items, written from bottom to top. 'add x' puts x at the top; 'take' removes the item at the top; 'copy' adds a copy of the top item at the top; 'turn' exchanges the top two items. The line holds at most 4 items: adding to a full one fails. An action that needs more items than there are fails and changes nothing.

Current state:
Seq: (empty)

Actions, in order:
1. turn

The questions are about the state after all these actions.
```
Question: Did at least one action fail? {}  → gold `True`

**Training row**

```
World: a line of items, written from bottom to top. 'add x' puts x at the top; 'take' removes the item at the top; 'copy' adds a copy of the top item at the top; 'turn' exchanges the top two items. The line holds at most 4 items: adding to a full one fails. An action that needs more items than there are fails and changes nothing.

Current state:
Seq: (empty)

Actions, in order:
1. turn

The questions are about the state after all these actions.
```
Questions: Did at least one action fail? {} → `True`

## B. same prompt, another question — seq, group T, item 6520
Match: training file `ftrain_mixG3` row 12072 (kind `floor`), identical prompt; state lines that differ: 0, action lines that differ: 0.

**Test item**

```
World: a line of items, written from bottom to top. 'add x' puts x at the top; 'take' removes the item at the top; 'copy' adds a copy of the top item at the top; 'turn' exchanges the top two items. The line holds at most 6 items: adding to a full one fails. An action that needs more items than there are fails and changes nothing.

Current state:
Seq: (empty)

Actions, in order:
1. take

The questions are about the state after all these actions.
```
Question: Did at least one action fail? {}  → gold `True`

**Training row**

```
World: a line of items, written from bottom to top. 'add x' puts x at the top; 'take' removes the item at the top; 'copy' adds a copy of the top item at the top; 'turn' exchanges the top two items. The line holds at most 6 items: adding to a full one fails. An action that needs more items than there are fails and changes nothing.

Current state:
Seq: (empty)

Actions, in order:
1. take

The questions are about the state after all these actions.
```
Questions: Which item is at the top? {"red": "red", "green": "green", "blue": "blue", "gold": "gold", "empty": "nothing, it is empty"} → `empty`

## C. near: same state and actions, other wording — seq, group T, item 5779
Match: training file `ftrain_mixG3` row 154028 (kind `multi`), Jaccard 0.8767; state lines that differ: 0, action lines that differ: 0.

**Test item**

```
World: a tray of items, written from front to back. 'add x' puts x at the back; 'take' removes the item at the front; 'copy' adds a copy of the front item at the back; 'turn' moves the front item to the back. An action that needs more items than there are fails and changes nothing.

Current state:
Seq: green red

Actions, in order:
1. add gold

The questions are about the state after all these actions.
```
Question: Which item is at the front? {"red": "red", "green": "green", "blue": "blue", "gold": "gold", "empty": "nothing, it is empty"}  → gold `green`

**Training row**

```
World: a list of items, written from front to back. 'add x' puts x at the back; 'take' removes the item at the front; 'copy' adds a copy of the front item at the back; 'turn' moves the front item to the back. An action that needs more items than there are fails and changes nothing.

Current state:
Seq: green red

Actions, in order:
1. add gold

The questions are about the state after all these actions.
```
Questions: Did at least one action fail? {} → `False`; Which item is at the front? {"red": "red", "green": "green", "blue": "blue", "gold": "gold", "empty": "nothing, it is empty"} → `green`; How many items are there? {"0": "0", "1": "1", "2": "2", "3": "3", "4": "4", "5": "5", "6": "6", "7": "7", "8": "8"} → `3`

## C. near: same state and actions, other wording — toggles, group T, item 5166
Match: training file `ftrain_mixG3` row 99606 (kind `floor`), Jaccard 0.5192; state lines that differ: 0, action lines that differ: 0.

**Test item**

```
World: 4 lamps numbered 1 to 4, each off / on, and 3 buttons. Pressing a button: B1 sets each of its lamps to on (lamp 2, lamp 3, lamp 4); B2 sets each of its lamps to on (lamp 2, lamp 3); B3 moves each of its lamps one step along the cycle off -> on -> off (lamp 2, lamp 3).

Current state:
lamp 1: off, lamp 2: off, lamp 3: off, lamp 4: on

Actions, in order:
1. press B2
2. press B3

The questions are about the state after all these actions.
```
Question: Are lamp 4 and lamp 2 in the same state? {}  → gold `False`

**Training row**

```
World: 4 lamps numbered 1 to 4, each off / on, and 3 buttons. Pressing a button: B1 sets each of its lamps to on (lamp 4); B2 sets each of its lamps to on (lamp 1, lamp 4); B3 moves each of its lamps one step along the cycle off -> on -> off (lamp 3).

Current state:
lamp 1: off, lamp 2: off, lamp 3: off, lamp 4: on

Actions, in order:
1. press B2
2. press B3

The questions are about the state after all these actions.
```
Questions: What state is lamp 1 in? {"off": "off", "on": "on"} → `on`

## D. near: same start state, other actions — seq, group T, item 6374
Match: training file `ftrain_mixG3` row 72924 (kind `floor`), Jaccard 0.6707; state lines that differ: 0, action lines that differ: 5.

**Test item**

```
World: a line of items, written from bottom to top. 'add x' puts x at the top; 'take' removes the item at the top; 'copy' adds a copy of the top item at the top; 'turn' exchanges the top two items. An action that needs more items than there are fails and changes nothing.

Current state:
Seq: 3

Actions, in order:
1. take
2. turn
3. add 2

The questions are about the state after all these actions.
```
Question: How many items are there? {"0": "0", "1": "1", "2": "2", "3": "3", "4": "4", "5": "5", "6": "6", "7": "7", "8": "8"}  → gold `1`

**Training row**

```
World: a line of items, written from bottom to top. 'add x' puts x at the top; 'take' removes the item at the top; 'copy' adds a copy of the top item at the top; 'turn' exchanges the top two items. An action that needs more items than there are fails and changes nothing.

Current state:
Seq: 3

Actions, in order:
1. turn
2. add 7

The questions are about the state after all these actions.
```
Questions: Which item is at the top? {"0": "0", "1": "1", "2": "2", "3": "3", "4": "4", "5": "5", "6": "6", "7": "7", "8": "8", "9": "9", "empty": "nothing, it is empty"} → `7`

## E. near: other start state, same actions — grid, group T, item 12
Match: training file `ftrain_mixG3` row 52134 (kind `read`), Jaccard 0.6519; state lines that differ: 6, action lines that differ: 0.

**Test item**

```
World: a bot on a 5x5 grid with columns 1 to 5 (left to right) and rows 1 to 5, row 1 at the top; a cell is named like (2,3), column first. 'north' moves one cell toward the top edge, 'south' toward the bottom edge, 'east' toward the right edge, 'west' toward the left edge. Walls cannot be entered. A move off the grid or into a wall is blocked and the bot stays. Entering a cell with a coin picks it up.

Current state:
Walls: (1,2), (1,4), (1,5), (5,5)
Coins: (2,2), (3,5)
Bot: (5,1)

Actions, in order:
1. move north

The questions are about the state after all these actions.
```
Question: In which cell is the bot? {"(1,1)": "cell (1,1)", "(2,1)": "cell (2,1)", "(3,1)": "cell (3,1)", "(4,1)": "cell (4,1)", "(5,1)": "cell (5,1)", "(1,2)": "cell (1,2)", "(2,2)": "cell (2,2)"  → gold `(5,1)`

**Training row**

```
World: a bot on a 5x5 grid with columns 1 to 5 (left to right) and rows 1 to 5, row 1 at the top; a cell is named like (2,3), column first. 'north' moves one cell toward the top edge, 'south' toward the bottom edge, 'east' toward the right edge, 'west' toward the left edge. Walls cannot be entered. A move off the grid or into a wall is blocked and the bot stays. Entering a cell with a coin picks it up.

Current state:
Walls: (1,4), (3,2)
Coins: (3,1), (4,2), (4,5), (5,1)
Bot: (2,4)

Actions, in order:
1. move north

The questions are about the state after all these actions.
```
Questions: Was at least one action blocked? {} → `False`

## F. near: other state and other actions (same family template) — grid, group T, item 527
Match: training file `mined_wide` row 534 (kind `floorM`), Jaccard 0.6279; state lines that differ: 6, action lines that differ: 2.

**Test item**

```
World: a drone on a 6x6 grid with columns A to F (left to right) and rows 1 to 6, row 1 at the bottom; a cell is named like B3. 'north' moves one cell toward the top edge, 'south' toward the bottom edge, 'east' toward the right edge, 'west' toward the left edge. Walls cannot be entered. A move off the grid or into a wall is blocked and the drone stays. Entering a cell with a star picks it up.

Current state:
Walls: C2, D1, D5
Stars: A5, B6, E2, F3
Drone: A1

Actions, in order:
1. move west
2. move south

The questions are about the state after all these actions.
```
Question: How many stars are left? {"0": "0", "1": "1", "2": "2", "3": "3", "4": "4"}  → gold `4`

**Training row**

```
World: a drone on a 6x6 grid with columns A to F (left to right) and rows 1 to 6, row 1 at the bottom; a cell is named like B3. 'north' moves one cell toward the top edge, 'south' toward the bottom edge, 'east' toward the right edge, 'west' toward the left edge. Walls cannot be entered. A move off the grid or into a wall is blocked and the drone stays. Entering a cell with a star picks it up.

Current state:
Walls: D6, E5
Stars: B1, B3, F1, F2
Drone: E2

Actions, in order:
1. move east
2. move south

The questions are about the state after all these actions.
```
Questions: How many stars are left? {"0": "0", "1": "1", "2": "2", "3": "3", "4": "4"} → `2`

## F. near: other state and other actions (same family template) — seq, group T, item 5946
Match: training file `ftrain_mixG3` row 162246 (kind `multi`), Jaccard 0.65; state lines that differ: 2, action lines that differ: 4.

**Test item**

```
World: a tray of items, written from bottom to top. 'add x' puts x at the top; 'take' removes the item at the top; 'copy' adds a copy of the top item at the top; 'turn' exchanges the top two items. The tray holds at most 4 items: adding to a full one fails. An action that needs more items than there are fails and changes nothing.

Current state:
Seq: S V U V

Actions, in order:
1. add S
2. turn
3. add S

The questions are about the state after all these actions.
```
Question: Which item is at the top? {"P": "P", "Q": "Q", "R": "R", "S": "S", "T": "T", "U": "U", "V": "V", "W": "W", "empty": "nothing, it is empty"}  → gold `U`

**Training row**

```
World: a tray of items, written from bottom to top. 'add x' puts x at the top; 'take' removes the item at the top; 'copy' adds a copy of the top item at the top; 'turn' exchanges the top two items. The tray holds at most 4 items: adding to a full one fails. An action that needs more items than there are fails and changes nothing.

Current state:
Seq: S V

Actions, in order:
1. copy

The questions are about the state after all these actions.
```
Questions: How many items are there? {"0": "0", "1": "1", "2": "2", "3": "3", "4": "4", "5": "5", "6": "6", "7": "7", "8": "8"} → `3`; Did at least one action fail? {} → `False`; Which item is at the top? {"P": "P", "Q": "Q", "R": "R", "S": "S", "T": "T", "U": "U", "V": "V", "W": "W", "empty": "nothing, it is empty"} → `V`

## F. near: other state and other actions (same family template) — counters, group T, item 3817
Match: training file `mined_wide` row 3323 (kind `floorM`), Jaccard 0.5481; state lines that differ: 2, action lines that differ: 5.

**Test item**

```
World: counters for points, bolts. 'add n X' adds n to X; 'remove n X' takes n from X. A removal costs a fee of 2 more from the same counter. A removal (with its fee) is rejected, changing nothing, if it would take the counter below -5. No counter can exceed 20: any amount above 20 is discarded.

Current state:
Counters: points 15, bolts 0

Actions, in order:
1. add 9 bolts
2. remove 3 bolts
3. remove 7 bolts

The questions are about the state after all these actions.
```
Question: Was action 1 rejected? {}  → gold `False`

**Training row**

```
World: counters for points, bolts. 'add n X' adds n to X; 'remove n X' takes n from X. A removal costs a fee of 2 more from the same counter. A removal (with its fee) is rejected, changing nothing, if it would take the counter below -5. No counter can exceed 20: any amount above 20 is discarded.

Current state:
Counters: points 7, bolts 3

Actions, in order:
1. remove 1 bolts
2. remove 1 bolts

The questions are about the state after all these actions.
```
Questions: Is bolts at 0 or below? {} → `True`

## F. near: other state and other actions (same family template) — gravity, group T, item 2504
Match: training file `ftrain_mixG3` row 110852 (kind `floor`), Jaccard 0.6116; state lines that differ: 6, action lines that differ: 1.

**Test item**

```
World: 4 vertical tubes numbered 1 to 4, each with 5 slots. A ball put into a tube falls down to the first free slot from the bottom. Slots are numbered from the bottom: slot 1 is the bottom slot. Putting a ball into a full tube loses the ball (the tube stays full).

Current state:
Tubes, from slot 1 onward:
tube 1: cat dog dog cat
tube 2: dog dog
tube 3: dog
tube 4: dog dog dog dog dog

Actions, in order:
1. put a cat ball into tube 2

The questions are about the state after all these actions.
```
Question: Is tube 2 full? {}  → gold `False`

**Training row**

```
World: 4 vertical tubes numbered 1 to 4, each with 5 slots. A ball put into a tube falls down to the first free slot from the bottom. Slots are numbered from the bottom: slot 1 is the bottom slot. Putting a ball into a full tube loses the ball (the tube stays full).

Current state:
Tubes, from slot 1 onward:
tube 1: cat dog dog cat
tube 2: cat cat dog
tube 3: dog dog cat
tube 4: cat dog

Actions, in order:
1. put a cat ball into tube 2
2. put a cat ball into tube 2

The questions are about the state after all these actions.
```
Questions: In which slot did the last ball end up? {"1": "slot 1", "2": "slot 2", "3": "slot 3", "4": "slot 4", "5": "slot 5", "none": "it did not enter the tube"} → `5`
