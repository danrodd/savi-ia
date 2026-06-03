import { describe, expect, it } from 'vitest'
import { toCsv } from '../csv'

describe('toCsv', () => {
  it('joins cells with commas and rows with CRLF', () => {
    expect(
      toCsv([
        ['a', 'b'],
        ['1', '2'],
      ]),
    ).toBe('a,b\r\n1,2')
  })

  it('quotes cells containing commas, quotes or newlines', () => {
    expect(toCsv([['x,y', 'a"b']])).toBe('"x,y","a""b"')
  })

  it('neutralizes formula injection with a leading apostrophe', () => {
    expect(toCsv([['=SUM(A1)', '+1', '-2', '@cmd']])).toBe("'=SUM(A1),'+1,'-2,'@cmd")
  })

  it('leaves safe numeric and text cells untouched', () => {
    expect(toCsv([['12500000', 'Farmacia X']])).toBe('12500000,Farmacia X')
  })
})
