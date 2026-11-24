import type { Answers } from './fhir'

// Made-up answers for demos. Only offered in development builds.
export const SAMPLE_ANSWERS: Answers = {
  'given-name': 'Sam',
  'family-name': 'Rivera-Test',
  'birth-date': '1988-09-14',
  gender: 'other',
  phone: '555-0117',
  reason: 'Sore throat and a fever since Saturday, hard to swallow.',
  'pain-score': '4',
  medications: 'Zyrtec most days in spring. I stopped taking omeprazole last month.',
  allergies: 'Amoxicillin gave me hives. Peanuts, I carry an EpiPen.',
  history: 'Asthma since I was a kid, use an albuterol inhaler a few times a month.',
  smoking: 'never',
  'weight-lb': '171',
}
