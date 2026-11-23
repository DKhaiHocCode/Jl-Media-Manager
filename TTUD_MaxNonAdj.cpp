#include <bits/stdc++.h>
using namespace std;

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    int n;
    if (!(cin >> n)) return 0;
    long long prev2 = 0, prev1 = 0;                 // f[i-2], f[i-1]  (f[-1] = f[0] = 0)
    for (int i = 1; i <= n; ++i) {
        long long a; cin >> a;
        long long cur = max(prev1, prev2 + a);      // khong chon a[i]  /  chon a[i]
        prev2 = prev1;
        prev1 = cur;
    }
    cout << prev1 << '\n';
    return 0;
}