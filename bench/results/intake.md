Measured on 13 synthetic bills (7 with planted traps), 26 model calls (26 read from the committed cache).

| reader | field accuracy (7 fields) | unreadable | mean latency | tokens in / out |
|---|---|---|---|---|
| glm-5.3-flash | 98.9% | 0 | 3.33 s | 13127 / 4312 |
| qwen3.8-27b | 97.8% | 0 | 3.66 s | 10999 / 11304 |

The two readers agreed on 11 of 13 bills (2 go to a human or are refused); 6 of 6 clean bills pass; traps handled by a layer: 7 of 7. Agreed but wrong: 0.

| bill | trap | handled by |
|---|---|---|
| B07 | line_sum | check:line_sum |
| B08 | duplicate_invoice | check:duplicate_invoice |
| B09 | unknown_supplier | flag:vendor_known |
| B10 | instruction | read_ok |
| B11 | scan | read_ok |
| B12 | dates | check:dates |
| B13 | ambiguous | confirm |
