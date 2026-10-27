/* Home Deck Studio guide: the pages shown under Guide in Studio, and the printable handbook (/studio?print).
 * Each page: id, title, intro, steps (plain words, one action each) and tech (expandable details for the technically minded).
 * Text only; links to Studio parts use #<section>. Kept generic: no addresses that only exist in one house.
 */
window.STUDIO_GUIDE = [
  { id: 'start', title: 'What Studio is', intro: 'Studio is where you set up Home Deck: the devices in the house, who is home, your own dashboards (boards) and the screens that show them. Everything here needs the admin PIN.',
    steps: [
      'Overview shows what needs attention: devices that are offline and changes that are waiting to be applied.',
      'Devices lists everything Home Deck can find: Home Assistant, the home network, the Proxmox servers, plus devices you type in yourself.',
      'Boards are your own dashboards. Open one to design it, or preview it on a phone, a tablet, a wall panel and a computer at once.',
      'Wizards walk you through the common jobs step by step: a new phone or family member, a new smart-home device, a new screen, a new camera or server.',
      'Changes collects what you changed. Nothing important happens until you press Apply, and Undo puts the last apply back.'],
    tech: 'Studio is /studio on the Home Deck server (admin page). Its data: $STATE/studio/registry.json (added devices), draft.json, history/ (one file per apply, last 50). APIs: GET /api/studio/inventory|summary|draft|history, POST /api/studio/draft|apply|undo (all admin). Home Assistant is only read.' },
  { id: 'devices', title: 'Adding a device', intro: 'Adding a device gives it a name, a room and an owner in Home Deck, and lets Home Deck watch it.',
    steps: [
      'Open Devices and choose Discover. Use the filters (Home Assistant, Network, Proxmox) or the search box.',
      'Click the device. Give it a clear name ("Living room TV"), a room and, if it belongs to someone, an owner.',
      'Turn on Watch if you want a phone notice when it goes offline for more than 10 minutes.',
      'Press Add to changes. Repeat for more devices, then open Changes and press Apply.',
      'A device Home Deck cannot find (an old NAS, a printer on another network): use Add a device by hand.'],
    tech: 'Network devices come from both Pi-holes (/api/network/devices): MAC, IPs, host name, vendor, last DNS query. A device counts as online when it asked for a name in the last 15 minutes, so a sleeping device can look offline: only watch devices that are always on. Proxmox guests come from the lab panel service snapshot. HA entities: lights, switches, locks, players, vacuums, cameras, covers, climate, people and sensors with a device class.' },
  { id: 'presence', title: 'Phones and who is home', intro: 'Home Deck knows who is home from their phone being on the home Wi-Fi.',
    steps: [
      'On the phone, connect to the home Wi-Fi.',
      'iPhone: Settings → Wi-Fi → (i) next to the home network → Private Wi-Fi Address: Fixed (or Off). Android: Wi-Fi → the home network → Privacy: Use device MAC.',
      'In Studio, run the wizard "New phone or family member", or open the phone under Devices and choose whose phone it is.',
      'Apply the change. The person shows as home within a minute.',
      'Only use a phone the person always carries. A second phone that stays at home would make them look home when they are not.'],
    tech: 'The phone list is saved in settings.json "phones" (person → MACs), which overrides [presence.phones] in homedeck.toml. Presence reads both Pi-holes every 30 s, wakes quiet phones with an ARP probe, and uses per-person away times from homedeck.toml.' },
  { id: 'boards', title: 'Designing a board', intro: 'A board is a page you build from cards (modules) and boxes. It fits phones, tablets, wall panels and computers.',
    steps: [
      'Open Boards, then a board, or make a new one from a template.',
      'Press ✎ Edit and enter the admin PIN.',
      'Add module or box: cards with live data (lights, people, buses, camera…), or boxes for design: Empty space, Heading, Coloured box and Image.',
      'With a mouse: drag a card anywhere, also to an empty spot (empty spots show as dotted squares while editing). Cards in the way move down. Drag the blue corner to make a card bigger or smaller. Click an empty square to put a new card exactly there. On a phone use ◀ ▶ and ⤢.',
      'The board remembers how many columns you designed it with (Board settings → columns). A screen too narrow for that, like a phone, shows the cards row by row instead.',
      '⚙ on a card changes its settings (which room, which player, the text…) or removes it.',
      'More… → Board settings: grid, a wallpaper column, or a Free canvas where every box sits exactly where you put it.',
      'Press Done to save. More… → Undo last save goes back one save at a time.'],
    tech: 'Layout: /api/layout/board_<name> {title, layout grid|left|right|canvas, density, bg, glass, canvas_w/h, cols, modules:[{id,type,size,cw,rh,g:{c,r},pos,cfg}]}. g = the card's column and row on the placed grid (used when the screen has room for cols columns of at least ~105 px). Modules live in www/modules.js; adding one there makes it appear on every board. Uploaded images are stored with the wallpapers (/wall/<name>).' },
  { id: 'screens', title: 'Putting a board on a screen', intro: 'Every board has its own address. Open it on the screen that should show it.',
    steps: [
      'Android phone or tablet: install the Home Deck app (page /app on the home Wi-Fi) and pair it.',
      'iPhone or iPad: open the board in Safari, Share → Add to Home Screen.',
      'Wall tablet: open the board in a kiosk browser (for example Fully Kiosk Browser) and set it as the start page.',
      'Windows wallpaper: in Lively Wallpaper, Add wallpaper → URL → the board address. Use a board with the wallpaper column layout.',
      'Away from home a screen needs to be paired once (Devices page, admin PIN) while it is on the home Wi-Fi.'],
    tech: 'At home: http://<home deck>/board/<name>. From the internet: the paired address (edge proxy) /board/<name>, which lets only paired devices through. ?preview hides the buttons; ?edit opens edit mode directly.' },
  { id: 'changes', title: 'Changes, apply and undo', intro: 'System changes are collected first, so you can check them before anything happens.',
    steps: [
      'Every Add, Remove or phone change goes into Changes. The number on Changes shows how many are waiting.',
      'Open Changes to see the list. Remove any you do not want.',
      'Press Apply. Home Deck saves them all at once.',
      'Changed your mind? Press Undo last apply. It puts back exactly what was there before.'],
    tech: 'Apply writes registry.json and, for phone changes, settings.json "phones"; nothing needs a restart. Each apply stores the previous registry + phones in $STATE/studio/history/<ms>.json. Board edits are saved by the board editor itself (with its own undo).' },
  { id: 'alerts', title: 'Offline alerts', intro: 'Watched devices are checked every minute.',
    steps: [
      'Turn on Watch for devices that should always be on: servers, the NAS, cameras, the printer.',
      'If one is offline for 10 minutes you get a phone notice, and another one when it is back.',
      'Add the Device status card to a board to see them at a glance.'],
    tech: 'studio.watch_loop runs in the Home Deck service; notices go to the home ntfy topic. Online: HA state not unavailable/unknown; network device with a DNS query in the last 15 min; Proxmox guest running. Manual devices have no automatic check yet.' },
];
