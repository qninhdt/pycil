import { expect,test } from 'vitest'

import { authErrorMessage,safeReturnTo } from '../../src/features/auth/flow'

test('post-auth destinations cannot leave the application subtree', () => {
  for (const value of ['https://evil.example', '//evil.example', '/app\\evil', '/application', '/login', '/app\n//evil']) expect(safeReturnTo(value)).toBe('/app')
  expect(safeReturnTo('/app/personal?create=deck')).toBe('/app/personal?create=deck')
  expect(authErrorMessage({ errors: [{ code: 'form_password_incorrect' }] })).toContain('email or password')
  expect(authErrorMessage({ errors: [{ code: 'form_identifier_not_found' }] })).toContain('email or password')
})
