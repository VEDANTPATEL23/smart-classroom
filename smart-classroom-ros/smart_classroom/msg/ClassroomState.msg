# What the monitor believes about the classroom after one frame.
Header header
uint32 students_present
uint32 phones_detected
string classroom_status    # NORMAL, WARNING or ALERT
string detected_zone       # LEFT, CENTER, RIGHT or NONE - where the phone is
string busiest_zone        # zone holding the most people, or NONE
uint32 left_count
uint32 center_count
uint32 right_count
bool status_changed        # true only on the frame the status flipped
bool zone_changed
uint32 event_count         # WARNING events inside the alert window
