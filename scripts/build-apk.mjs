// Runs the Gradle debug build for the Android app (see README "Android app").
// Called by `npm run android:apk` after the web build and `cap sync`. The full
// path matters: cmd.exe may be set not to run programs from the current folder.
// The APK is then copied into public/downloads/ so the website's landing page
// can offer it to Field Responders (see MobileAppSection.tsx).
import { execSync } from 'node:child_process'
import { copyFileSync, mkdirSync } from 'node:fs'
import { resolve } from 'node:path'

const androidDir = resolve('android')
const gradlew = resolve(androidDir, process.platform === 'win32' ? 'gradlew.bat' : 'gradlew')
execSync(`"${gradlew}" assembleDebug`, { cwd: androidDir, stdio: 'inherit' })

const apk = resolve(androidDir, 'app/build/outputs/apk/debug/app-debug.apk')
const download = resolve('public/downloads/RescueEye-FieldResponder.apk')
mkdirSync(resolve('public/downloads'), { recursive: true })
copyFileSync(apk, download)
console.log('\nAPK: android/app/build/outputs/apk/debug/app-debug.apk')
console.log('Website download: public/downloads/RescueEye-FieldResponder.apk')
