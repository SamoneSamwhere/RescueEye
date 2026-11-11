/**
 * In-app instructions, one set per role. Written for someone opening
 * RescueEye for the first time: what each screen is for, then the steps, using
 * the exact names of the buttons they will see.
 *
 * A guide's `id` is also how a page opens its own guide from the "How this
 * page works" button (components/help/PageHelpButton.tsx), so keep ids stable.
 */
import type { UserRole } from '../../types/user'

export interface Guide {
  id: string
  title: string
  /** One sentence: what this is for. */
  summary: string
  steps?: string[]
  /** Things worth knowing that are not steps. */
  notes?: string[]
}

export interface GlossaryEntry {
  term: string
  meaning: string
}

export interface RoleHelp {
  /** What this role does, in one or two sentences. */
  intro: string
  /** The big picture: the order things usually happen in. */
  quickStart: string[]
  guides: Guide[]
  glossary: GlossaryEntry[]
  /** Common problems and what to do. */
  troubleshooting: GlossaryEntry[]
}

const COMMAND_STAFF: RoleHelp = {
  intro:
    'You run the operation from the console: connect drones, watch their video while the AI looks for casualties, confirm what it finds, and send Field Responders. The AI never acts on its own. Every incident and every alert starts with your decision.',
  quickStart: [
    'Form your team on My Team: the 3 nearest available Field Responders.',
    'Register and connect your drone on Drones.',
    'Watch its video on Live Monitoring. The AI marks people as it finds them.',
    'When a "Possible casualty" card pops up, open it in Detection Review.',
    'Check the evidence, then Verify (your team is alerted) or Reject.',
    'Follow the rescue on Incidents and the Damage Map until you close the incident.',
  ],
  guides: [
    {
      id: 'my-team',
      title: 'Form your team',
      summary: 'Each commander leads one team of Field Responders for the operation. Every casualty you verify is sent to it.',
      steps: [
        'Open My Team.',
        'Choose the area: press Use my location, or pick an open incident.',
        'Choose the team size (3 by default). RescueEye lists the nearest available responders who are not on another team.',
        'Press Form team. Each member sees "You\'re on Team …" on their phone.',
        'To swap someone, press Replace: the next nearest available responder takes their place.',
        'Press Disband team when the operation is over.',
      ],
      notes: [
        'A responder can be on only one team, so two commanders never get the same person.',
        'If a member declines a mission, RescueEye sends the next nearest available responder instead and puts them on your team. You get a message saying who.',
        'Each team gets a callsign: Alpha, Bravo, Charlie, and so on.',
      ],
    },
    {
      id: 'drones',
      title: 'Connect a drone',
      summary: 'Only registered drones can stream into RescueEye.',
      steps: [
        'Open Drones and press Register Drone. Enter its name and serial number.',
        'Press Connect Drone and choose the drone.',
        'Copy the address shown (it starts with rtmp://). The phone must be on the same Wi-Fi as this computer.',
        'In DJI Fly on the phone: Transmission → Live Streaming Platforms → RTMP. Paste the address and start streaming.',
        'The feed opens on Live Monitoring by itself.',
      ],
      notes: [
        'DJI Fly sends video but no GPS. To place casualties on the map, have the pilot turn on "I\'m flying it" in the Field Responder app, so the pilot\'s phone location is used.',
      ],
    },
    {
      id: 'live-monitoring',
      title: 'Watch live video',
      summary: 'Each drone feed plays full-size with the AI running over it.',
      steps: [
        'Open Live Monitoring. Each connected drone has its own panel.',
        'Set Camera to Straight down or Angled to match the drone\'s camera. The AI judges casualties differently for each, so a wrong setting causes mistakes.',
        'Leave AI detection on (the button at the top) and read the boxes as they appear (see the colours below).',
        'Press Stop Feed when you are done with a drone.',
      ],
      notes: [
        'Red box: possible casualty. Green box: a person who looks fine (walking, standing). Orange: fire. Dashed grey: smoke.',
        'The badge at the bottom left names the damage around the drone (fire, flood, collapse). It is hidden when there is no damage.',
        'The counter at the top right reads "1 casualty · 3 OK", meaning one possible casualty and three people who look fine.',
        'LIVE means a real drone right now. Recorded means a clip from the Media Library.',
      ],
    },
    {
      id: 'casualty-popup',
      title: 'The "Possible casualty" pop-up',
      summary: 'When the AI is at least 75% sure it sees a casualty, a red card slides in, whatever page you are on.',
      steps: [
        'Read the card: the photo, how sure the AI is, and why.',
        'Press Verify casualty to confirm it straight away, or Open in Detection Review to look closer first.',
        'Press × if it is clearly wrong. You can still find it in Detection Review.',
      ],
      notes: [
        'The card fades away after 15 seconds. Hovering over it pauses the countdown. A casualty whose card faded is never lost; it waits in Detection Review.',
      ],
    },
    {
      id: 'detection-review',
      title: 'Review and verify a detection',
      summary: 'Everything the AI found waits here until a person decides. This is the only place an incident is created.',
      steps: [
        'Open Detection Review and pick a detection from the queue on the right.',
        'Check the photo and the AI output: confidence, location, suggested priority and suggested team.',
        'If it is real, press Verify & Dispatch. Add notes and check the priority. Your team is already chosen: its available members will be alerted.',
        'If the casualty needs more people than your team has, the nearest free responders are added as backup. They join your team.',
        'Press the confirm button. To alert different people, open "Change who is alerted" first.',
        'If it is wrong, press Reject and say why. This helps improve the AI.',
      ],
      notes: [
        'No team yet? You can still tick responders by hand, but forming a team on My Team makes every verification one click.',
        'Suggested Team estimates how many responders this casualty needs (for example 4 or more when someone is partly buried). It comes from the Jev AI model, or from simple rules when there is no internet. It is only a suggestion; you decide.',
        'A detection with no location cannot be verified. Fix the drone\'s position first (see "I\'m flying it").',
        'You can verify without alerting anyone and alert responders later from the same screen.',
      ],
    },
    {
      id: 'media-library',
      title: 'Upload recorded video',
      summary: 'Run the AI over footage recorded earlier, filed under the incident it was filmed at.',
      steps: [
        'Open Media Library and press Add Video.',
        'Choose the video file, the incident it was filmed at, and the drone that recorded it.',
        'Optional: add the .SRT file DJI saves beside the video (turn on Video Captions in DJI Fly). It holds the drone\'s GPS.',
        'Press Upload. RescueEye reads where the video was filmed and starts the AI on it straight away.',
        'Casualties it finds appear in Detection Review, placed where the drone was at that moment of the video.',
      ],
      notes: [
        'You can only upload to an open incident. If there is none, verify a detection first.',
        'Footage filmed more than 1 km from the incident is refused, so a clip from somewhere else cannot be filed under it.',
        'A video with no GPS is refused unless you tick "simulate it at the incident". Simulated clips are clearly marked.',
        'The Filmed at column shows where each clip was recorded. Click it to see the spot on a map.',
      ],
    },
    {
      id: 'incidents',
      title: 'Follow and close an incident',
      summary: 'Every verified detection becomes an incident you can track until the rescue is over.',
      steps: [
        'Open Incidents to see all incidents with their priority and status. Use the filters to narrow the list.',
        'Open one to see its responders, their progress and the original detection.',
        'When the rescue is over, press Close Incident.',
      ],
    },
    {
      id: 'damage-map',
      title: 'Read the Damage Map',
      summary: 'Everything with a location, on one map.',
      notes: [
        'Red dots are incidents, yellow are verified detections, light blue are your Field Responders, purple are drones (the circle around a drone shows how far off its position may be).',
        'Numbered bubbles are groups of nearby markers. Zoom in or click them to split them up.',
        'Organizations in this area: other agencies working within 5 km of your open incidents. The lead organization is green and the others are blue. The lead is whoever has been working the area longest; when it finishes, the next one takes over and the colours change by themselves.',
        'Other agencies\' responders show as dots without names. RescueEye never shares names or phone numbers between agencies.',
        'Rehearsal: "Add a sample organization" places a made-up agency near your incident so you can practise. Only your agency sees it.',
      ],
    },
    {
      id: 'logs',
      title: 'Check the logs',
      summary: 'A record of everything that happened across your incidents, newest first. Click an entry to see the detection behind it.',
    },
  ],
  glossary: [
    { term: 'Detection', meaning: 'Something the AI found in the video. Only a suggestion until a person reviews it.' },
    { term: 'Possible casualty', meaning: 'A person the AI thinks needs help: lying down, not moving, or partly buried.' },
    { term: 'Person (green)', meaning: 'Someone the AI saw and judged to be fine. Shown on the video only; never stored or alerted.' },
    { term: 'Verify', meaning: 'Your confirmation that a detection is real. It creates an incident.' },
    { term: 'Incident', meaning: 'A confirmed situation that responders work on, from verification until you close it.' },
    { term: 'Confidence', meaning: 'How sure the AI is, from 0 to 100%.' },
    { term: 'Simulated position', meaning: 'A made-up location used for demos or when the drone sends no GPS. Always labelled.' },
    { term: 'Lead organization', meaning: 'The agency in charge of an area: the one that has been working there longest.' },
  ],
  troubleshooting: [
    { term: 'The feed says "Stream unavailable"', meaning: 'Check the phone is still streaming and on the same Wi-Fi, then press Retry stream.' },
    { term: 'No boxes appear', meaning: 'Check AI detection is on. The AI only shows casualties in red and fine people in green; an empty scene shows nothing.' },
    { term: 'Too many casualties on people walking', meaning: 'Set Camera to Angled if the drone camera is tilted forward.' },
    { term: 'A detection has no location', meaning: 'The drone sent no GPS. Have the pilot turn on "I\'m flying it" in the Field Responder app.' },
    { term: 'Upload refused', meaning: 'Read the message: the video was filmed too far from the incident, or has no GPS. Add the DJI .SRT file, or tick simulate for a demo.' },
  ],
}

const FIELD_RESPONDER: RoleHelp = {
  intro:
    'You go where you are needed. Command Staff alert you to a confirmed casualty; your phone guides you there, and you report your progress so the console always knows where the rescue stands.',
  quickStart: [
    'Sign in on the RescueEye app and allow location and notifications.',
    'Wait on Home: it says "Standing by for dispatch" until you are alerted.',
    'When an alert arrives, press Accept (or Decline if you cannot go).',
    'Press Start Navigation and follow the route.',
    'Press Arrive On-Site when you get there, and Report Rescue Complete when it is done.',
  ],
  guides: [
    {
      id: 'first-time',
      title: 'First time on the app',
      summary: 'The app needs to know where the RescueEye server is and where you are.',
      steps: [
        'On the sign-in screen, check the Server address. On the same Wi-Fi as the console laptop it looks like http://192.168.x.x:8000. Ask your Command Staff if unsure.',
        'Sign in with the email and password your Agency Admin gave you.',
        'Allow location (so you can be sent to the nearest casualty) and notifications (so alerts reach you).',
      ],
    },
    {
      id: 'missions',
      title: 'Respond to an alert',
      summary: 'Each alert is a mission: one casualty, with its location and priority.',
      steps: [
        'Open the alert. It shows the priority, the incident type and the location.',
        'Press Accept to take it, or Decline if you cannot go. Declining lets Command Staff send someone else quickly.',
        'Press Start Navigation, then Open Navigation for the route.',
        'Press Arrive On-Site when you reach the casualty.',
        'Press Report Rescue Complete when the rescue is finished.',
      ],
      notes: [
        'Your status (Alerted, Accepted, En Route, On Site, Cleared) shows live on the Command Staff console.',
        'Home shows which team you are on ("You\'re on Team Alpha"), who leads it and who you go out with. Your whole team is alerted together.',
        'If you decline, the next nearest available responder is sent instead.',
      ],
    },
    {
      id: 'pilot',
      title: 'Flying the drone',
      summary: 'Most drones send video without GPS. Your phone can stand in for it.',
      steps: [
        'On Home, find the Drone pilot card.',
        'Type the drone\'s name exactly as it appears in Connect Drone, then press I\'m flying it. Your phone\'s location is used as the drone\'s, so casualties appear near the right spot on the map.',
        'Press Stop — I\'ve landed when you land.',
      ],
      notes: ['Your phone is near the drone, not under it, so the map shows a wide circle rather than an exact point.'],
    },
    {
      id: 'map',
      title: 'The map',
      summary: 'Incidents and other responders around you. Your own marker is labelled "You".',
    },
  ],
  glossary: [
    { term: 'Mission', meaning: 'Your assignment to one incident.' },
    { term: 'Priority', meaning: 'How urgent the incident is: Low, Medium, High or Critical.' },
    { term: 'Cleared', meaning: 'You reported the rescue complete.' },
  ],
  troubleshooting: [
    { term: 'Alerts are not arriving', meaning: 'Check notifications are allowed for RescueEye and you are signed in.' },
    { term: 'Cannot sign in', meaning: 'Check the Server address on the sign-in screen, and that your phone is on the same Wi-Fi as the console laptop.' },
  ],
}

const AGENCY_ADMIN: RoleHelp = {
  intro:
    'You manage your organization\'s people. You create the accounts for your Command Staff and Field Responders, switch them on or off, and can see the teams and missions they have worked.',
  quickStart: [
    'Your organization is approved by the System Admin; you can now sign in.',
    'Open Manage Personnel and press Add to create each staff account.',
    'Give each person their email and temporary password.',
    'Watch Response Teams and Mission History as your staff respond.',
  ],
  guides: [
    {
      id: 'add-staff',
      title: 'Add a staff member',
      summary: 'Create an account for a Command Staff member or a Field Responder.',
      steps: [
        'Open Manage Personnel and press Add.',
        'Fill in their name, email and mobile number.',
        'Choose a role: Command Staff run the console; Field Responders go to the field with the phone app.',
        'Set a temporary password (at least 8 characters) and press Create User.',
        'The new person appears highlighted at the top of the list. Share the email and password with them securely.',
      ],
    },
    {
      id: 'personnel',
      title: 'Find, activate or deactivate staff',
      summary: 'Search, filter and switch accounts on or off.',
      steps: [
        'Search by name or email, or filter by role.',
        'Sort by Newest first or Name (A–Z).',
        'Press Deactivate to stop someone signing in (for example, they left). Press Activate to let them back in. Nothing is deleted.',
      ],
    },
    {
      id: 'teams',
      title: 'Response Teams and Mission History',
      summary: 'See who Command Staff sent where.',
      notes: [
        'Standing teams: the team each Command Staff member leads (Team Alpha, Bravo, …) and who is on it.',
        'Incident teams: who went to each incident and whether they are still working.',
        'Mission History lists every mission your Field Responders have been sent on, with its priority and outcome.',
      ],
    },
  ],
  glossary: [
    { term: 'Command Staff', meaning: 'Run the console: drones, AI review, verifying incidents and sending responders.' },
    { term: 'Field Responder', meaning: 'Goes to casualties using the phone app.' },
    { term: 'Inactive', meaning: 'The account exists but cannot sign in.' },
  ],
  troubleshooting: [
    { term: '"A user with this email address already exists"', meaning: 'That email has an account already. Search for it in Manage Personnel; it may be inactive.' },
  ],
}

const SYSTEM_ADMIN: RoleHelp = {
  intro:
    'You decide which organizations may use RescueEye. You review each registration and its documents, approve or reject it, and can switch an approved agency off.',
  quickStart: [
    'Open Agency Validation to see registrations waiting for review.',
    'Press Review on one. Its details and documents open in a side panel.',
    'Open each document and check it matches the organization.',
    'Press Accept, Reject (with a reason) or Request Resubmission.',
  ],
  guides: [
    {
      id: 'validation',
      title: 'Review a registration',
      summary: 'Every new organization waits here until you decide.',
      steps: [
        'Open Agency Validation. The tabs split Pending Review, Needs Resubmission and Rejected.',
        'Press Review. The panel shows the agency, its admin and its documents.',
        'Click a document to open it full-screen.',
        'Press Accept to approve: the agency becomes active and its admin can sign in.',
        'Press Reject, or Request Resubmission to ask for corrections. Both ask you for a reason, which the agency sees.',
      ],
      notes: ['A rejected registration can be reopened later from the Rejected tab.'],
    },
    {
      id: 'manage-agency',
      title: 'Manage approved agencies',
      summary: 'Switch an approved agency on or off.',
      steps: ['Open Manage Agency.', 'Press Deactivate to stop the whole agency signing in, or Activate to restore it. Nothing is deleted.'],
    },
  ],
  glossary: [
    { term: 'Pending Review', meaning: 'A new registration waiting for your decision.' },
    { term: 'Needs Resubmission', meaning: 'You asked for corrections; waiting for the agency to resubmit.' },
  ],
  troubleshooting: [],
}

export const HELP_BY_ROLE: Partial<Record<UserRole, RoleHelp>> = {
  COMMAND_STAFF: COMMAND_STAFF,
  FIELD_RESPONDER: FIELD_RESPONDER,
  AGENCY_ADMIN: AGENCY_ADMIN,
  SYSTEM_ADMIN: SYSTEM_ADMIN,
}

export function findGuide(role: UserRole, id: string): Guide | undefined {
  return HELP_BY_ROLE[role]?.guides.find((g) => g.id === id)
}
