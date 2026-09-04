"""Dev check: does the untuned scorer score the failure segment moderately?"""
import pandas as pd

from app.scorer import score

df = pd.read_csv("data/cases.csv", dtype={"case_id": str})


def s(r):
    return score({
        "failure_class": r.failure_class,
        "amount": r.amount,
        "customer_tenure_months": r.customer_tenure_months,
        "prior_failure_count": r.prior_failure_count,
        "payment_method": r.payment_method,
        "merchant_category": r.merchant_category,
    })


df["p"] = df.apply(s, axis=1)
seg = df[(df.failure_class == "insufficient_funds") & (df.prior_failure_count >= 3)]
print("SEGMENT: n=%d  mean=%.3f  median=%.3f" % (len(seg), seg.p.mean(), seg.p.median()))
print("  send_message band (0.4-0.7): %.1f%%" % (100 * ((seg.p >= 0.4) & (seg.p < 0.7)).mean()))
print("  retry band (>=0.7)         : %.1f%%" % (100 * (seg.p >= 0.7).mean()))
print("  true recoverable rate      : %.3f" % seg.true_recoverable.mean())
print("  avg segment amount         : Rs %.0f" % seg.amount.mean())
exp = seg[(seg.p >= 0.4) & (seg.p < 0.7)]
if len(exp):
    exp_rec = exp.true_recoverable.mean() * exp.amount.mean()
    print("  messaged cases n=%d  expected recovered/case Rs %.0f vs cost Rs 300"
          % (len(exp), exp_rec))
