#include <bits/stdc++.h>
using namespace std;

int main() {
    int n, k, m;
    if (!(cin >> n >> k >> m)) return 0;
    vector<int> a(n);
    for (auto &x : a) cin >> x;

    vector<vector<long long>> dp(k + 1, vector<long long>(m + 1, 0));
    dp[0][0] = 1;                                   
    for (int i = 0; i < n; ++i)                     
        for (int j = min(i + 1, k); j >= 1; --j)    // duyet NGUOC de moi phan tu chi dung 1 lan
            for (int s = m; s >= a[i]; --s)
                dp[j][s] += dp[j - 1][s - a[i]];

    cout << dp[k][m] << '\n';
    return 0;