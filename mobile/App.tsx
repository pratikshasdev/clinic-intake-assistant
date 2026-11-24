import { StatusBar } from 'expo-status-bar'
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native'
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context'

import { API_URL, api } from './src/api'
import {
  buildQuestionnaireResponse,
  displayAnswer,
  pages,
  range,
  validatePage,
  type Answers,
  type Questionnaire,
  type QuestionnaireItem,
} from './src/fhir'
import { SAMPLE_ANSWERS } from './src/sample'

type Screen =
  | { name: 'loading' }
  | { name: 'unreachable'; message: string }
  | { name: 'welcome' }
  | { name: 'page'; index: number }
  | { name: 'review' }
  | { name: 'done'; firstName: string }

export default function App() {
  return (
    <SafeAreaProvider>
      <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
        <StatusBar style="dark" />
        <Intake />
      </SafeAreaView>
    </SafeAreaProvider>
  )
}

function Intake() {
  const [questionnaire, setQuestionnaire] = useState<Questionnaire | null>(null)
  const [screen, setScreen] = useState<Screen>({ name: 'loading' })
  const [answers, setAnswers] = useState<Answers>({})
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setScreen({ name: 'loading' })
    try {
      setQuestionnaire(await api.questionnaire())
      setScreen({ name: 'welcome' })
    } catch (e) {
      setScreen({ name: 'unreachable', message: (e as Error).message })
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const groups = useMemo(() => (questionnaire ? pages(questionnaire) : []), [questionnaire])

  const setAnswer = (linkId: string, value: string) => {
    setAnswers((a) => ({ ...a, [linkId]: value }))
    setErrors((e) => {
      if (!e[linkId]) return e
      const { [linkId]: _, ...rest } = e
      return rest
    })
  }

  const next = (index: number) => {
    const pageErrors = validatePage(groups[index], answers)
    setErrors(pageErrors)
    if (Object.keys(pageErrors).length > 0) return
    setScreen(index + 1 < groups.length ? { name: 'page', index: index + 1 } : { name: 'review' })
  }

  const submit = async () => {
    if (!questionnaire) return
    setSubmitting(true)
    setSubmitError(null)
    try {
      await api.submit(buildQuestionnaireResponse(questionnaire, answers))
      setScreen({ name: 'done', firstName: answers['given-name']?.trim() ?? '' })
    } catch (e) {
      setSubmitError((e as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  const startOver = () => {
    setAnswers({})
    setErrors({})
    setSubmitError(null)
    setScreen({ name: 'welcome' })
  }

  switch (screen.name) {
    case 'loading':
      return (
        <Centered>
          <ActivityIndicator size="large" color={colors.accent} />
          <Text style={styles.muted}>Loading the check-in form…</Text>
        </Centered>
      )

    case 'unreachable':
      return (
        <Centered>
          <Text style={styles.title}>Can't reach the clinic</Text>
          <Text style={styles.body}>{screen.message}</Text>
          <Text style={styles.muted}>Trying {API_URL}</Text>
          <Button label="Try again" onPress={load} />
        </Centered>
      )

    case 'welcome':
      return (
        <Centered>
          <Text style={styles.kicker}>Check in</Text>
          <Text style={styles.title}>{questionnaire?.title ?? 'Patient check-in'}</Text>
          <Text style={styles.body}>
            A few questions about you and today's visit. It takes about two minutes, and the front desk will review
            your answers before your visit.
          </Text>
          <Button label="Start" onPress={() => setScreen({ name: 'page', index: 0 })} />
          {__DEV__ && (
            <Pressable
              accessibilityRole="button"
              onPress={() => {
                setAnswers(SAMPLE_ANSWERS)
                setScreen({ name: 'review' })
              }}
            >
              <Text style={styles.link}>Fill in sample answers (demo)</Text>
            </Pressable>
          )}
        </Centered>
      )

    case 'page': {
      const group = groups[screen.index]
      return (
        <Page
          step={`Step ${screen.index + 1} of ${groups.length}`}
          title={group.text ?? ''}
          onBack={() => setScreen(screen.index === 0 ? { name: 'welcome' } : { name: 'page', index: screen.index - 1 })}
          primary={{ label: screen.index + 1 < groups.length ? 'Next' : 'Review', onPress: () => next(screen.index) }}
        >
          {(group.item ?? []).map((item) => (
            <Field
              key={item.linkId}
              item={item}
              value={answers[item.linkId] ?? ''}
              error={errors[item.linkId]}
              onChange={(v) => setAnswer(item.linkId, v)}
            />
          ))}
        </Page>
      )
    }

    case 'review':
      return (
        <Page
          step="Last step"
          title="Check your answers"
          onBack={() => setScreen({ name: 'page', index: groups.length - 1 })}
          primary={{ label: submitting ? 'Sending…' : 'Send to the front desk', onPress: submit, disabled: submitting }}
        >
          {groups.map((group, index) => (
            <View key={group.linkId} style={styles.card}>
              <View style={styles.cardHeader}>
                <Text style={styles.cardTitle}>{group.text}</Text>
                <Pressable accessibilityRole="button" onPress={() => setScreen({ name: 'page', index })}>
                  <Text style={styles.link}>Edit</Text>
                </Pressable>
              </View>
              {(group.item ?? []).map((item) => {
                const shown = displayAnswer(item, answers[item.linkId])
                return (
                  <View key={item.linkId} style={styles.reviewRow}>
                    <Text style={styles.reviewLabel}>{item.text}</Text>
                    <Text style={shown ? styles.reviewValue : styles.muted}>{shown || 'Skipped'}</Text>
                  </View>
                )
              })}
            </View>
          ))}
          {submitError && <Text style={styles.error}>{submitError}</Text>}
        </Page>
      )

    case 'done':
      return (
        <Centered>
          <Text style={styles.check}>✓</Text>
          <Text style={styles.title}>{screen.firstName ? `Thanks, ${screen.firstName}` : 'Thanks'}</Text>
          <Text style={styles.body}>You're checked in. Please take a seat, and we'll call you shortly.</Text>
          <Button label="Done" onPress={startOver} variant="quiet" />
        </Centered>
      )
  }
}

function Page({
  step,
  title,
  onBack,
  primary,
  children,
}: {
  step: string
  title: string
  onBack: () => void
  primary: { label: string; onPress: () => void; disabled?: boolean }
  children: React.ReactNode
}) {
  return (
    <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={styles.header}>
        <Pressable accessibilityRole="button" onPress={onBack} hitSlop={12}>
          <Text style={styles.link}>Back</Text>
        </Pressable>
        <Text style={styles.muted}>{step}</Text>
      </View>
      <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
        <Text style={styles.title}>{title}</Text>
        {children}
      </ScrollView>
      <View style={styles.footer}>
        <Button label={primary.label} onPress={primary.onPress} disabled={primary.disabled} />
      </View>
    </KeyboardAvoidingView>
  )
}

function Field({
  item,
  value,
  error,
  onChange,
}: {
  item: QuestionnaireItem
  value: string
  error?: string
  onChange: (value: string) => void
}) {
  const label = (
    <Text style={styles.label}>
      {item.text}
      {item.required ? '' : <Text style={styles.muted}> (optional)</Text>}
    </Text>
  )

  let control: React.ReactNode
  const { min, max } = range(item)
  if (item.type === 'choice') {
    control = (
      <View style={styles.options}>
        {(item.answerOption ?? []).map(({ valueCoding }) => (
          <Option
            key={valueCoding.code}
            label={valueCoding.display ?? valueCoding.code}
            selected={value === valueCoding.code}
            onPress={() => onChange(value === valueCoding.code ? '' : valueCoding.code)}
          />
        ))}
      </View>
    )
  } else if (item.type === 'integer' && min != null && max != null && max - min <= 10) {
    control = (
      <View style={styles.scale}>
        {Array.from({ length: max - min + 1 }, (_, i) => String(min + i)).map((n) => (
          <Option key={n} label={n} compact selected={value === n} onPress={() => onChange(value === n ? '' : n)} />
        ))}
      </View>
    )
  } else {
    const multiline = item.type === 'text'
    control = (
      <TextInput
        style={[styles.input, multiline && styles.multiline, error ? styles.inputError : null]}
        value={value}
        onChangeText={onChange}
        multiline={multiline}
        textAlignVertical={multiline ? 'top' : 'center'}
        placeholder={item.type === 'date' ? 'YYYY-MM-DD' : multiline ? 'Type in your own words' : undefined}
        placeholderTextColor={colors.placeholder}
        keyboardType={
          item.type === 'integer'
            ? 'number-pad'
            : item.type === 'decimal'
              ? 'decimal-pad'
              : item.linkId === 'phone'
                ? 'phone-pad'
                : 'default'
        }
        autoCapitalize={item.type === 'date' ? 'none' : 'sentences'}
        accessibilityLabel={item.text}
      />
    )
  }

  return (
    <View style={styles.field}>
      {label}
      {control}
      {error && <Text style={styles.error}>{error}</Text>}
    </View>
  )
}

function Option({
  label,
  selected,
  compact,
  onPress,
}: {
  label: string
  selected: boolean
  compact?: boolean
  onPress: () => void
}) {
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={[styles.option, compact && styles.optionCompact, selected && styles.optionSelected]}
    >
      <Text style={[styles.optionText, selected && styles.optionTextSelected]}>{label}</Text>
    </Pressable>
  )
}

function Button({
  label,
  onPress,
  disabled,
  variant = 'primary',
}: {
  label: string
  onPress: () => void
  disabled?: boolean
  variant?: 'primary' | 'quiet'
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        variant === 'quiet' && styles.buttonQuiet,
        (pressed || disabled) && styles.buttonPressed,
      ]}
    >
      <Text style={[styles.buttonText, variant === 'quiet' && styles.buttonTextQuiet]}>{label}</Text>
    </Pressable>
  )
}

function Centered({ children }: { children: React.ReactNode }) {
  return <View style={styles.centered}>{children}</View>
}

const colors = {
  bg: '#f6f7f9',
  surface: '#ffffff',
  border: '#dfe3e8',
  text: '#1b1f24',
  muted: '#5f6b7a',
  placeholder: '#9aa3ae',
  accent: '#2459d6',
  accentSoft: '#e8eefc',
  error: '#b3261e',
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  flex: { flex: 1 },
  centered: { flex: 1, justifyContent: 'center', padding: 24, gap: 16 },
  header: { flexDirection: 'row', justifyContent: 'space-between', paddingHorizontal: 20, paddingVertical: 12 },
  scroll: { padding: 20, paddingTop: 4, gap: 20 },
  footer: { padding: 20, paddingTop: 8, borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  kicker: { color: colors.accent, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 1 },
  title: { fontSize: 26, fontWeight: '700', color: colors.text },
  body: { fontSize: 17, lineHeight: 24, color: colors.text },
  muted: { fontSize: 15, color: colors.muted },
  link: { fontSize: 16, color: colors.accent, fontWeight: '600' },
  check: { fontSize: 56, color: colors.accent },
  field: { gap: 8 },
  label: { fontSize: 17, fontWeight: '600', color: colors.text, lineHeight: 23 },
  input: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 17,
    color: colors.text,
  },
  multiline: { minHeight: 110 },
  inputError: { borderColor: colors.error },
  error: { color: colors.error, fontSize: 15 },
  options: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  scale: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  option: {
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  optionCompact: { width: 44, paddingHorizontal: 0, alignItems: 'center', borderRadius: 12 },
  optionSelected: { backgroundColor: colors.accentSoft, borderColor: colors.accent },
  optionText: { fontSize: 16, color: colors.text },
  optionTextSelected: { color: colors.accent, fontWeight: '600' },
  button: { backgroundColor: colors.accent, borderRadius: 14, paddingVertical: 16, alignItems: 'center' },
  buttonQuiet: { backgroundColor: colors.accentSoft },
  buttonPressed: { opacity: 0.7 },
  buttonText: { color: '#ffffff', fontSize: 17, fontWeight: '600' },
  buttonTextQuiet: { color: colors.accent },
  card: {
    backgroundColor: colors.surface,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: colors.border,
    padding: 16,
    gap: 12,
  },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  cardTitle: { fontSize: 17, fontWeight: '700', color: colors.text },
  reviewRow: { gap: 2 },
  reviewLabel: { fontSize: 14, color: colors.muted },
  reviewValue: { fontSize: 16, color: colors.text },
})
