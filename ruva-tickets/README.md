# RÜVA ticket system

Files
- tickets_singles.pdf / tickets_doubles.pdf : print these (8 tickets per A4 page)
- scanner.html : the gate scanner (open on the gate phone)
- tickets.csv : your master list (who bought what). KEEP PRIVATE.
- secret.key : the signing secret. KEEP PRIVATE. Anyone with it can make valid fake tickets. Do not upload or share it.
- config.json : event name, date, time, venue, prices

Ticket artwork (Blue Hour Vol. 01 design is already applied)
- The design image lives in assets/design_source.jpg (single ticket on top, double ticket below).
- To use a new design image:  python3 ruva_tickets.py design path/to/new_image.jpg
  This keeps the SAME tickets and secret key and only re-draws the PDFs with real QR codes.
- After editing config.json or the artwork, run:  python3 ruva_tickets.py render
- Never run `generate --force` once anything is printed or sold: it creates brand-new tickets and the old ones stop working.

Selling (activate a ticket when it is sold; unsold tickets are rejected at the gate)
  python3 ruva_tickets.py sell S-001 S-002 --buyer "Ama" --phone 0244000000 --seller Kojo
Then send the rebuilt scanner.html to the gate phone. See totals with:
  python3 ruva_tickets.py report

Gate
- Open scanner.html in Chrome (Android). QR text looks like S-001.BB891F01B2207BCD. The camera needs https, so host the file free (Netlify Drop / GitHub Pages / Cloudflare Pages).
- Green = let in. Red = turn away. Orange = ticket was never sold.
- Doubles allow 2 entries (they can arrive separately).
- Use ONE phone per gate. Scan history lives on that phone only.
- Camera not working? Type the serial and the 4-letter CODE printed under the QR.
