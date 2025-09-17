import io
import pandas as pd
from typing import List, Dict, Any

def rows_to_csv_bytes(rows: List[Dict[str, Any]]) -> bytes:
    import pandas as pd
    df = pd.DataFrame(rows, columns=["Document", "(Sub)Section #", "(Sub)Section Name", "Specification", "Pass"])
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")
