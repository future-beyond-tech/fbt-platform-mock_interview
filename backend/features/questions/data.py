"""features/questions/data.py — Static question catalogue (single source of truth).

Migrated verbatim from backend/questions.py.  The old questions.py now
re-exports from here so any code that still imports from the top-level module
continues to work without changes.

The frontend previously had a duplicate copy in src/data/questions.js —
that file should be deleted and all question data fetched from GET /api/questions
(Phase 4 acceptance criterion).
"""

from __future__ import annotations

QUESTIONS: list[dict] = [
    {"id": "jb01", "q": "What is the difference between var, let, and const? Explain hoisting and the temporal dead zone (TDZ).", "s": "JS Core", "day": 1},
    {"id": "jb02", "q": "What is the difference between primitive types and reference types? How does JavaScript store each in memory?", "s": "JS Core", "day": 1},
    {"id": "jb03", "q": "What is type coercion? What is the output of `[] + {}` and `{} + []` — and explain why.", "s": "JS Core", "day": 1},
    {"id": "jb04", "q": "What is the difference between a function declaration and a function expression? How does hoisting affect each?", "s": "JS Core", "day": 1},
    {"id": "jb05", "q": "What is the scope chain? What is lexical scoping and how does it work in JavaScript?", "s": "JS Core", "day": 1},
    {"id": "jb06", "q": "What is a closure? Write a function factory that uses a closure to create independent counters.", "s": "JS Core", "day": 1},
    {"id": "jb07", "q": 'Explain the 4 ways "this" can be bound in JavaScript. What do .call(), .apply(), and .bind() each do?', "s": "JS Core", "day": 1},
    {"id": "jb08", "q": "What is the prototype chain? What is the difference between __proto__ and .prototype?", "s": "JS Core", "day": 1},
    {"id": "jb09", "q": "What is the difference between spread and rest operators? Give examples with arrays, objects, and function params.", "s": "JS Core", "day": 1},
    {"id": "jb10", "q": "What is optional chaining (?.) and nullish coalescing (??)? How does ?? differ from ||?", "s": "JS Core", "day": 1},
    {"id": "ap01", "q": "What is the difference between map() and forEach()? When would you choose reduce() over map + filter?", "s": "Array Problems", "day": 1},
    {"id": "ap02", "q": "Write a function to remove duplicates from an array without using Set. Show two different approaches.", "s": "Array Problems", "day": 1},
    {"id": "ap03", "q": "Write a function to flatten a deeply nested array without using Array.flat(). Explain your approach.", "s": "Array Problems", "day": 1},
    {"id": "ap04", "q": "Implement Array.prototype.map() from scratch without using any built-in array methods.", "s": "Array Problems", "day": 1},
    {"id": "ap05", "q": "Given an array of objects, group them by a specific property using only reduce(). Walk through the logic.", "s": "Array Problems", "day": 1},
    {"id": "ap06", "q": "Write a function that returns the intersection of two arrays, and another for the difference.", "s": "Array Problems", "day": 1},
    {"id": "ap07", "q": "Write a chunk(arr, n) function that splits an array into sub-arrays of size n. Handle edge cases.", "s": "Array Problems", "day": 1},
    {"id": "ap08", "q": "What is the difference between slice() and splice()? Does sort() mutate the original array?", "s": "Array Problems", "day": 1},
    {"id": "ap09", "q": "Solve Two Sum: given an array and target, return indices of the two numbers that add up to target. Explain the O(n) approach.", "s": "Array Problems", "day": 1},
    {"id": "ap10", "q": "Implement Kadane's algorithm to find the maximum subarray sum. Walk through the logic step by step.", "s": "Array Problems", "day": 1},
    {"id": "op01", "q": "What is the difference between Object.keys(), Object.values(), Object.entries(), and Object.fromEntries()?", "s": "Object Problems", "day": 1},
    {"id": "op02", "q": "What is the difference between a shallow copy and a deep copy? What are the limitations of JSON.parse(JSON.stringify(obj))?", "s": "Object Problems", "day": 1},
    {"id": "op03", "q": "Write a deepMerge(obj1, obj2) function that recursively merges two objects including nested objects and arrays.", "s": "Object Problems", "day": 1},
    {"id": "op04", "q": 'Write a flatten(obj) function that converts a nested object to dot-notation keys: {a:{b:1}} → {"a.b":1}.', "s": "Object Problems", "day": 1},
    {"id": "op05", "q": "Implement pick(obj, keys) and omit(obj, keys) that return new objects with or without the specified keys.", "s": "Object Problems", "day": 1},
    {"id": "op06", "q": "Write a deepEqual(a, b) function that recursively compares two values — objects, arrays, primitives.", "s": "Object Problems", "day": 1},
    {"id": "op07", "q": "What does Object.defineProperty() do? Explain enumerable, configurable, and writable property descriptors.", "s": "Object Problems", "day": 1},
    {"id": "op08", "q": "Write a function to invert the keys and values of an object. Handle duplicate values.", "s": "Object Problems", "day": 1},
    {"id": "op09", "q": "Write a function that counts character frequency in a string and returns a frequency map object.", "s": "Object Problems", "day": 1},
    {"id": "op10", "q": "What is the difference between Object.freeze() and Object.seal()? Is freeze deep? How do you deep-freeze?", "s": "Object Problems", "day": 1},
    {"id": "ja01", "q": "Explain the JavaScript event loop. What is the difference between the callback queue and the microtask queue?", "s": "JS Advanced", "day": 2},
    {"id": "ja02", "q": "What is the exact output and why? console.log(1); setTimeout(()=>console.log(2),0); Promise.resolve().then(()=>console.log(3)); console.log(4)", "s": "JS Advanced", "day": 2},
    {"id": "ja03", "q": "What is the difference between Promise.all(), Promise.race(), Promise.allSettled(), and Promise.any()? Give a use case for each.", "s": "JS Advanced", "day": 2},
    {"id": "ja04", "q": "How do you handle errors in async/await? What is the difference between sequential vs parallel promise execution?", "s": "JS Advanced", "day": 2},
    {"id": "ja05", "q": "What are generators? Write an infinite ID sequence generator using function* and yield. What is the iterator protocol?", "s": "JS Advanced", "day": 2},
    {"id": "ja06", "q": "Implement a curry(fn) function that supports partial application: curry(add)(1)(2) === 3.", "s": "JS Advanced", "day": 2},
    {"id": "ja07", "q": "Implement a memoize(fn) function that caches results. How do you handle multiple arguments as the cache key?", "s": "JS Advanced", "day": 2},
    {"id": "ja08", "q": "What is the difference between Map and WeakMap, Set and WeakSet? When would you use the Weak variants?", "s": "JS Advanced", "day": 2},
    {"id": "ja09", "q": "What is a Proxy in JavaScript? Write a Proxy that validates property types on assignment and throws if invalid.", "s": "JS Advanced", "day": 2},
    {"id": "ja10", "q": "Explain the Observer pattern. Implement a simple EventEmitter with on(event, fn), off(event, fn), and emit(event, data).", "s": "JS Advanced", "day": 2},
    {"id": "rb01", "q": "What does JSX compile to? What does React.createElement() return? Describe the virtual DOM tree for a simple component.", "s": "React Basics", "day": 2},
    {"id": "rb02", "q": "What is the difference between a controlled and an uncontrolled component? When would you choose one over the other?", "s": "React Basics", "day": 2},
    {"id": "rb03", "q": "What are the Rules of Hooks? Why can't you call hooks inside a condition, loop, or nested function?", "s": "React Basics", "day": 2},
    {"id": "rb04", "q": "What is the difference between useState(0) and useState(() => expensiveCalc())? When do you use the initializer form?", "s": "React Basics", "day": 2},
    {"id": "rb05", "q": "Explain useEffect's dependency array. What happens with no array, an empty array [], or [count]? When does cleanup run?", "s": "React Basics", "day": 2},
    {"id": "rb06", "q": "What is the difference between stopPropagation() and preventDefault() in React? Give an example for each.", "s": "React Basics", "day": 2},
    {"id": "rb07", "q": "Why does React require a key prop on list items? What happens with missing, duplicate, or index-based keys?", "s": "React Basics", "day": 2},
    {"id": "rb08", "q": "What is a SyntheticEvent in React? How does React's event delegation differ from native DOM event delegation?", "s": "React Basics", "day": 2},
    {"id": "rb09", "q": "What is the difference between props and state? Can a child modify its parent's state directly?", "s": "React Basics", "day": 2},
    {"id": "rb10", "q": "Write a fully controlled form with two fields that validates on submit, shows inline errors, and resets on success.", "s": "React Basics", "day": 2},
    {"id": "ra01", "q": "What is the difference between useRef and useState? When do you use useRef to hold a value without triggering a re-render?", "s": "React Advanced", "day": 3},
    {"id": "ra02", "q": "When should you use useMemo? What are the real costs of over-memoizing? Give a concrete example where it genuinely helps.", "s": "React Advanced", "day": 3},
    {"id": "ra03", "q": "When should you use useCallback? Explain the stale closure problem in React hooks and how useCallback relates to it.", "s": "React Advanced", "day": 3},
    {"id": "ra04", "q": "What rules must a custom hook follow? Write a useFetch(url) hook that returns {data, loading, error} and cancels on unmount.", "s": "React Advanced", "day": 3},
    {"id": "ra05", "q": "What is the Context API? When should you NOT use it? What are the re-rendering performance pitfalls?", "s": "React Advanced", "day": 3},
    {"id": "ra06", "q": "How does React.memo work internally? What is shallow comparison? When does React.memo fail to prevent re-renders?", "s": "React Advanced", "day": 3},
    {"id": "ra07", "q": "What is code splitting in React? How do React.lazy and Suspense work together, and what is the trade-off?", "s": "React Advanced", "day": 3},
    {"id": "ra08", "q": "What is an Error Boundary? Why can't functional components be error boundaries? Write an error boundary class component.", "s": "React Advanced", "day": 3},
    {"id": "ra09", "q": "What is useTransition in React 18? Give a real-world use case. How is useDeferredValue different?", "s": "React Advanced", "day": 3},
    {"id": "ra10", "q": "Explain React's reconciliation algorithm and the Fiber architecture. Why is the key prop critical to diffing?", "s": "React Advanced", "day": 3},
    {"id": "ra11", "q": "A React component tree is re-rendering too often and the UI is janky. Walk me through your full debugging and optimization process.", "s": "React Advanced", "day": 3},
    {"id": "ba01", "q": "Write a complete Todo app with add, edit, delete, and filter (all/active/completed) using only useState — no libraries.", "s": "Build & Practice", "day": 3},
    {"id": "ba02", "q": "Write a custom useLocalStorage(key, initialValue) hook that keeps state in sync with localStorage, with SSR safety.", "s": "Build & Practice", "day": 3},
    {"id": "ba03", "q": "Build a data-fetching component using useEffect that handles loading, error, empty, and success states cleanly.", "s": "Build & Practice", "day": 3},
    {"id": "ba04", "q": "Implement useDebounce(value, delay) and use it in a search input that only fires an API call after the user stops typing.", "s": "Build & Practice", "day": 3},
    {"id": "ba05", "q": "Build a reusable useForm(initialValues, rules) hook that tracks field values, errors, touched state, and exposes handleSubmit.", "s": "Build & Practice", "day": 3},
    {"id": "ba06", "q": "Walk me through deploying a React app. How does your AWS ROSA experience fit into a frontend CI/CD pipeline?", "s": "Build & Practice", "day": 3},
    {"id": "ba07", "q": "Do a code review of a React component. Name 5 common issues you would flag in a senior pull request.", "s": "Build & Practice", "day": 3},
]

_DAY_COUNTS: dict[int, int] = {
    1: sum(1 for q in QUESTIONS if q["day"] == 1),
    2: sum(1 for q in QUESTIONS if q["day"] == 2),
    3: sum(1 for q in QUESTIONS if q["day"] == 3),
}

SESSIONS: list[dict] = [
    {"id": "all", "name": "Full Interview", "sub": f"All {len(QUESTIONS)} questions", "col": "#3B82F6", "filter": None},
    {"id": "d1", "name": "Day 1 · JS Foundations", "sub": f"{_DAY_COUNTS[1]} questions · Core JS + Arrays + Objects", "col": "#F59E0B", "filter": 1},
    {"id": "d2", "name": "Day 2 · JS Advanced + React", "sub": f"{_DAY_COUNTS[2]} questions", "col": "#10B981", "filter": 2},
    {"id": "d3", "name": "Day 3 · React Advanced + Build", "sub": f"{_DAY_COUNTS[3]} questions", "col": "#8B5CF6", "filter": 3},
]
