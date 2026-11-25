/** A translated namespace has exactly the keys of its English source, all strings. */
export type Translations<T> = { [K in keyof T]: string };
