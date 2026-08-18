"""Synthetic 15-complaint judging set.

The real 15-complaint set is revealed at judging. This synthetic set is designed
to stress the SAME failure modes the judges will probe:
  - same issue filed in different languages (Tamil/Hindi/English/Tanglish)
  - same issue described with very different vocabulary
  - two DISTINCT issues at nearby locations (dedup must NOT over-merge)
  - voice-style messy text (no punctuation, angry, low-text)
  - complaints with and without locations

Each entry has a `truth_cluster` key = the ground-truth issue group.

Cluster map (ground truth):
  A: pothole on Anna Nagar 2nd Avenue near school       (complaints 1,4,8,12)
  B: garbage pile near Koyambedu market                 (complaints 2,6,9)
  C: broken streetlight on T. Nagar Usman Road          (complaints 3,7,11,14)
  D: waterlogging on Velachery main road                (complaints 5,10)
  E: pothole on Mount Road near a petrol pump           (complaints 13,15)  <- distinct from A (different location)
"""
COMPLAINTS = [
    {"id": 1, "channel": "text", "language": "en", "text": "Big deep pothole on 2nd Avenue Anna Nagar near the school. Cars are braking hard and one scooter almost fell. Please fix urgently.",
     "lat": 13.084, "lng": 80.221, "truth": "A"},
    {"id": 2, "channel": "text", "language": "en", "text": "Huge garbage dump near the Koyambedu market entrance. Smells terrible, rats everywhere. Two days now.",
     "lat": 13.072, "lng": 80.212, "truth": "B"},
    {"id": 3, "channel": "text", "language": "en", "text": "Streetlight not working on Usman Road, T Nagar. The whole stretch is dark at night, very unsafe.",
     "lat": 13.041, "lng": 80.234, "truth": "C"},
    {"id": 4, "channel": "text", "language": "ta", "text": "அண்ணா நகர் செகண்ட் அவென்யூல பெரிய குழி இருக்கு. பள்ளிக்கூடத்துக்கு பக்கத்துல. வேகமா போற வண்டி கவுன்சிலு விழும்போல இருக்கு.",
     "lat": 13.0842, "lng": 80.2208, "truth": "A"},
    {"id": 5, "channel": "text", "language": "en", "text": "Water is logged upto knee level on Velachery Main Road after the rain. Autos and bikes getting stuck in the water.",
     "lat": 12.979, "lng": 80.219, "truth": "D"},
    {"id": 6, "channel": "text", "language": "hi", "text": "कोयम्बेडू बाज़ार के पास कचरे का बड़ा ढेर लगा है। दो दिनों से जमा है और बदबू आ रही है।",
     "lat": 13.0718, "lng": 80.2123, "truth": "B"},
    {"id": 7, "channel": "text", "language": "en", "text": "The street lamp outside Metro station T Nagar Usman road has not lit up in a week. Dark spot, afraid to walk.",
     "lat": 13.0405, "lng": 80.2342, "truth": "C"},
    {"id": 8, "channel": "voice", "language": "ta", "transcript": "சாலையில் பெரிய குழி இருக்கிறது. வண்டிகள் எல்லாம் வேகம் குறைச்சிட்டு போகுது. பள்ளிக்கூடத்துக்கு பக்கத்துல. தயவு செய்து சரி பண்ணுங்க.",
     "lat": 13.0845, "lng": 80.2213, "truth": "A"},
    {"id": 9, "channel": "text", "language": "en", "text": "garbage garbage garbage near koyambedu market stinking pile please clear it!!!!",
     "lat": 13.0722, "lng": 80.2125, "truth": "B"},
    {"id": 10, "channel": "voice", "language": "en", "transcript": "Velachery main road water logging, vehicles stuck, please drain the water",
     "lat": 12.9792, "lng": 80.2188, "truth": "D"},
    {"id": 11, "channel": "text", "language": "hi", "text": "उस्मान रोड टी नगर में स्ट्रीट लाइट खराब है, रात में अंधेरा रहता है, डर लगता है",
     "lat": 13.0408, "lng": 80.2338, "truth": "C"},
    {"id": 12, "channel": "voice", "language": "hi", "transcript": "अन्ना नगर दूसरी एवेन्यू पर स्कूल के पास बड़ा गड्ढा है, कृपया ठीक करें",
     "lat": 13.0838, "lng": 80.2211, "truth": "A"},
    {"id": 13, "channel": "text", "language": "en", "text": "Pothole in front of the petrol pump on Mount Road, near the flyover. Big one.",
     "lat": 13.061, "lng": 80.246, "truth": "E"},
    {"id": 14, "channel": "text", "language": "en", "text": "No street lighting on Usman Road T Nagar - lamp post broken completely, pole leaning",
     "lat": 13.0413, "lng": 80.2345, "truth": "C"},
    {"id": 15, "channel": "text", "language": "ta", "text": "மவுண்ட் ரோடுல பெட்ரோல் பங்க் முன்னாடி பெரிய குழி இருக்கு",
     "lat": 13.0612, "lng": 80.2461, "truth": "E"},
]

GROUND_TRUTH = {
    "A": ["pothole", "Anna Nagar", "2nd Avenue"],
    "B": ["garbage", "Koyambedu"],
    "C": ["streetlight", "Usman Road", "T Nagar"],
    "D": ["waterlogging", "Velachery"],
    "E": ["pothole", "Mount Road"],
}

if __name__ == "__main__":
    from collections import Counter
    counts = Counter(c["truth"] for c in COMPLAINTS)
    print("Ground-truth cluster sizes:", dict(counts))
    print(f"Total complaints: {len(COMPLAINTS)}, unique issues: {len(counts)}")
