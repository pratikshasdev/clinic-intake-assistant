// The app knows nothing about the clinic's questions. It renders whatever
// FHIR Questionnaire the server returns and sends back a QuestionnaireResponse.

export type Coding = { system?: string; code: string; display?: string }

export type QuestionnaireItem = {
  linkId: string
  text?: string
  type: string
  required?: boolean
  item?: QuestionnaireItem[]
  answerOption?: Array<{ valueCoding: Coding }>
  extension?: Array<{ url: string; valueInteger?: number; valueDecimal?: number }>
}

export type Questionnaire = {
  resourceType: 'Questionnaire'
  id?: string
  url?: string
  version?: string
  title?: string
  item: QuestionnaireItem[]
}

/** Raw answers as the patient typed or picked them, keyed by linkId. A choice stores its code. */
export type Answers = Record<string, string>

const MIN_VALUE = 'http://hl7.org/fhir/StructureDefinition/minValue'
const MAX_VALUE = 'http://hl7.org/fhir/StructureDefinition/maxValue'

export function range(item: QuestionnaireItem): { min?: number; max?: number } {
  const find = (url: string) => item.extension?.find((e) => e.url === url)
  const min = find(MIN_VALUE)
  const max = find(MAX_VALUE)
  return { min: min?.valueInteger ?? min?.valueDecimal, max: max?.valueInteger ?? max?.valueDecimal }
}

export function pages(q: Questionnaire): QuestionnaireItem[] {
  return q.item.filter((i) => i.type === 'group')
}

export function displayAnswer(item: QuestionnaireItem, raw: string | undefined): string {
  if (!raw) return ''
  if (item.type === 'choice') {
    return item.answerOption?.find((o) => o.valueCoding.code === raw)?.valueCoding.display ?? raw
  }
  return raw.trim()
}

/** Returns an error message per linkId for the items on one page. Empty object means the page is fine. */
export function validatePage(group: QuestionnaireItem, answers: Answers, today = new Date()): Record<string, string> {
  const errors: Record<string, string> = {}
  for (const item of group.item ?? []) {
    const raw = (answers[item.linkId] ?? '').trim()
    if (!raw) {
      if (item.required) errors[item.linkId] = 'Please fill this in.'
      continue
    }
    if (item.type === 'date') {
      const parsed = parseDate(raw)
      if (!parsed) errors[item.linkId] = 'Use the format YYYY-MM-DD, for example 1985-07-21.'
      else if (parsed > today) errors[item.linkId] = 'That date is in the future.'
      else if (parsed.getUTCFullYear() < 1900) errors[item.linkId] = 'Please check the year.'
    }
    if (item.type === 'integer' || item.type === 'decimal') {
      const n = Number(raw)
      const { min, max } = range(item)
      if (!Number.isFinite(n) || (item.type === 'integer' && !Number.isInteger(n))) {
        errors[item.linkId] = item.type === 'integer' ? 'Please enter a whole number.' : 'Please enter a number.'
      } else if ((min != null && n < min) || (max != null && n > max)) {
        errors[item.linkId] = `Please pick a number from ${min ?? '…'} to ${max ?? '…'}.`
      } else if (n < 0) {
        errors[item.linkId] = 'Please enter a positive number.'
      }
    }
  }
  return errors
}

function parseDate(raw: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(raw)
  if (!m) return null
  const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])))
  return d.getUTCMonth() === Number(m[2]) - 1 && d.getUTCDate() === Number(m[3]) ? d : null
}

function toAnswer(item: QuestionnaireItem, raw: string | undefined): Record<string, unknown> | null {
  const value = (raw ?? '').trim()
  if (!value) return null
  switch (item.type) {
    case 'choice': {
      const option = item.answerOption?.find((o) => o.valueCoding.code === value)
      return option ? { valueCoding: option.valueCoding } : null
    }
    case 'date':
      return { valueDate: value }
    case 'integer':
      return { valueInteger: Number(value) }
    case 'decimal':
      return { valueDecimal: Number(value) }
    default:
      return { valueString: value }
  }
}

export function buildQuestionnaireResponse(q: Questionnaire, answers: Answers) {
  const groups = pages(q)
    .map((group) => ({
      linkId: group.linkId,
      text: group.text,
      item: (group.item ?? []).flatMap((item) => {
        const answer = toAnswer(item, answers[item.linkId])
        return answer ? [{ linkId: item.linkId, text: item.text, answer: [answer] }] : []
      }),
    }))
    .filter((g) => g.item.length > 0)

  return {
    resourceType: 'QuestionnaireResponse' as const,
    questionnaire: q.url && q.version ? `${q.url}|${q.version}` : q.url,
    status: 'completed' as const,
    authored: new Date().toISOString(),
    item: groups,
  }
}
