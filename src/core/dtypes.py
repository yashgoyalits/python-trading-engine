import numpy as np

MAX_SYMBOLS          = 10
MAX_TICKS_PER_SYMBOL = 200
MAX_CANDLE_HISTORY   = 20
MAX_ACTIVE_TRADES    = 5
MAX_TRAILING         = 5
MAX_LOGS             = 20
MAX_ORDERS           = 32   # ring buffer

TF_30S = 30
TF_1M  = 60
TF_3M  = 180

TICK_DTYPE = np.dtype([
    ('seq',        np.uint64),
    ('timestamp',  np.float64),
    ('ltp',        np.float64),
    ('volume',     np.int64),
    ('open_price', np.float64),
    ('high_price', np.float64),
    ('low_price',  np.float64),
    ('prev_close', np.float64),
])

CANDLE_DTYPE = np.dtype([
    ('seq',        np.uint64),
    ('open',       np.float64),
    ('high',       np.float64),
    ('low',        np.float64),
    ('close',      np.float64),
    ('volume',     np.int64),
    ('start_time', np.float64),
])

# Per-symbol control — seq counters + write indices + bucket tracking
CTRL_DTYPE = np.dtype([
    ('tick_seq',        np.uint64),
    ('tick_widx',       np.uint32),

    ('c30s_seq',        np.uint64),
    ('c30s_widx',       np.uint32),
    ('c30s_bucket',     np.int64),

    ('c1m_seq',         np.uint64),
    ('c1m_widx',        np.uint32),
    ('c1m_bucket',      np.int64),

    ('c3m_seq',         np.uint64),
    ('c3m_widx',        np.uint32),
    ('c3m_bucket',      np.int64),

    ('_pad',            np.uint8, (4,)),
])

ORDER_DTYPE = np.dtype([
    ('seq',          np.uint64),
    ('status',       np.int8),
    ('order_type',   np.int8),
    ('side',         np.int8),
    ('_pad',         np.uint8, (5,)),
    ('qty',          np.int32),
    ('stop_price',   np.float64),
    ('limit_price',  np.float64),
    ('traded_price', np.float64),
    ('order_id',     'S64'),
    ('parent_id',    'S64'),
    ('symbol',       'S32'),
    ('order_datetime',   'S32'),
])

TRAILING_DTYPE = np.dtype([
    ('threshold', np.float64),
    ('new_stop',  np.float64),
    ('hit',       np.bool_),
    ('_pad',      np.uint8, (7,)),
])

TRADE_DTYPE = np.dtype([
    ('active',          np.bool_),
    ('_pad1',           np.uint8, (3,)),
    ('trade_no',        np.int32),
    ('qty',             np.int32),
    ('side',            np.int8),
    ('trailing_count',  np.int8),
    ('_pad2',           np.uint8, (6,)),
    ('entry_price',     np.float64),
    ('stop_price',      np.float64),
    ('target_price',    np.float64),
    ('order_id',        'S64'),
    ('stop_order_id',   'S64'),
    ('target_order_id', 'S64'),
    ('symbol',          'S32'),
    ('strategy_id',     'S32'),
    ('trailing',        TRAILING_DTYPE, (MAX_TRAILING,)),
])

LOG_DTYPE = np.dtype([
    ('seq',       np.uint64),
    ('timestamp', np.float64),
    ('level',     np.uint8),    # 10=DEBUG 20=INFO 30=WARN 40=ERROR
    ('_pad',      np.uint8, (7,)),
    ('message',   'S256'),
])

# Global order ring buffer control
ORDER_CTRL_DTYPE = np.dtype([
    ('widx', np.uint32),
    ('seq',  np.uint64),
])

LOG_CTRL_DTYPE = np.dtype([
    ('widx', np.uint32),
    ('seq',  np.uint64),
])
