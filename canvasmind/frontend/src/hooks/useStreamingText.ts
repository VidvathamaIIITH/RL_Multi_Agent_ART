import { useState, useEffect, useRef } from 'react'

export function useStreamingText(targetText: string, speed: number = 15): string {
  const [displayed, setDisplayed] = useState('')
  const indexRef = useRef(0)
  const prevTargetRef = useRef('')

  useEffect(() => {
    if (targetText === prevTargetRef.current) return

    if (targetText.startsWith(prevTargetRef.current)) {
      // Appending — continue from current position
    } else {
      // New text — reset
      setDisplayed('')
      indexRef.current = 0
    }

    prevTargetRef.current = targetText

    if (indexRef.current >= targetText.length) return

    const interval = setInterval(() => {
      indexRef.current += speed
      setDisplayed(targetText.slice(0, indexRef.current))
      if (indexRef.current >= targetText.length) {
        setDisplayed(targetText)
        clearInterval(interval)
      }
    }, 16)

    return () => clearInterval(interval)
  }, [targetText, speed])

  return displayed
}
