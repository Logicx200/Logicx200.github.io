import inspect
import lowtran

for name in ["transmittance", "radiance", "horiztrans", "horizrad", "userhoriztrans", "scenarios"]:
    f = getattr(lowtran, name)
    print("=" * 20, name, "=" * 20)
    print(inspect.signature(f))
    doc = inspect.getdoc(f)
    print((doc[:1500] + "...") if doc else "(no doc)")
    print()
