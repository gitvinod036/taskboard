// Centralised programming-language registry for the coding UI.
//
// Mirrors backend/taskflow/languages.py (the backend remains authoritative
// when validating a submission). Only used here for friendly display names
// and Monaco syntax modes — never for executing code.

export const PROGRAMMING_LANGUAGES = {
  python: { name: 'Python', monaco: 'python', extension: '.py' },
  javascript: { name: 'JavaScript', monaco: 'javascript', extension: '.js' },
  cpp: { name: 'C++', monaco: 'cpp', extension: '.cpp' },
  java: { name: 'Java', monaco: 'java', extension: '.java' },
}

export const DEFAULT_LANGUAGE = 'python'

export function isSupportedLanguage(identifier) {
  return Boolean(PROGRAMMING_LANGUAGES[identifier])
}

export function languageDisplayName(identifier) {
  const entry = PROGRAMMING_LANGUAGES[identifier]
  return entry ? entry.name : identifier || ''
}

export function monacoLanguage(identifier) {
  const entry = PROGRAMMING_LANGUAGES[identifier]
  return entry ? entry.monaco : 'plaintext'
}

export function starterCodeFor(problem, identifier) {
  const starters = problem?.starter_code || {}
  if (typeof starters[identifier] === 'string' && starters[identifier].length > 0) {
    return starters[identifier]
  }
  // No stored starter for this language: give an empty editor rather than
  // pretending there is one.
  return ''
}

export function languagesForProblem(problem) {
  const allowed = Array.isArray(problem?.allowed_languages) ? problem.allowed_languages : []
  return allowed.filter((id) => isSupportedLanguage(id))
}
